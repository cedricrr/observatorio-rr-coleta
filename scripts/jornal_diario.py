"""Orquestrador do jornal editorial diário.

Pipeline ponta a ponta: garante PDF no R2 (via coletor inline se
necessário), processa pelos estágios 8.1-8.7, renderiza HTML
consolidado de todas as fontes do dia.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from scripts.baixar_pdf import baixar_pdf_do_r2
from scripts.classificar import classificar_materia
from scripts.cliente_anthropic import ClienteAnthropic
from scripts.coletar import processar_fonte
from scripts.config import get_fonte
from scripts.filtrar import filtrar_materias
from scripts.pdf_para_markdown import pdf_para_markdown
from scripts.r2_client import R2Client
from scripts.renderizar import renderizar_jornal
from scripts.segmentar import Materia, segmentar_materias
from scripts.sidecar import montar_sidecar
from scripts.validador_sensivel import aplicar_filtro_sensivel

logger = logging.getLogger(__name__)

FONTES_VALIDAS = ("MPRR", "TJRR")
OUTPUT_DIR_DEFAULT = Path("/tmp/observatorio-roraima")


def coletar_dia(
    fonte_codigo: str, data_alvo: date, r2: R2Client,
) -> str | None:
    """Wrapper sobre processar_fonte; retorna chave R2 do PDF (ou None).

    processar_fonte já faz dedup internamente via r2.existe antes de
    baixar. A chave real do PDF (que pode incluir sufixo de edição
    no caso do MPRR) é extraída do campo url_r2 do dict retornado.
    """
    try:
        fonte_obj = get_fonte(fonte_codigo.lower())
        resultado = processar_fonte(fonte_obj, data_alvo, r2)
        if resultado is None:
            return None
        url_r2 = resultado.get("url_r2")
        if not url_r2:
            return None
        return urlparse(url_r2).path.lstrip("/")
    except Exception as e:
        logger.warning(
            f"Coleta de {fonte_codigo} para {data_alvo} falhou: {e}"
        )
        return None


def processar_chave(
    chave: str,
    fonte_codigo: str,
    r2: R2Client,
    cliente: ClienteAnthropic,
) -> list[Materia]:
    """Pipeline de publicação a partir de uma chave R2 já conhecida.

    Não re-coleta: baixa o PDF da chave informada, converte, segmenta,
    filtra e classifica. Usado pelo backfill de publicação (Ciclo 10.6),
    que conhece a chave pelos JSONs locais e não deve re-discover nos
    portais (discover de data antiga pode falhar e gerar jornal vazio
    mesmo com o PDF já no R2). Resiliente por estágio: falha de
    pipeline → []; falha de classificação de UMA matéria → pula.
    """
    try:
        pdf_bytes = baixar_pdf_do_r2(chave, r2)
        markdown = pdf_para_markdown(pdf_bytes)
        pdf_url = r2.url_publica(chave)
        materias_brutas = segmentar_materias(
            markdown, fonte_codigo, pdf_url,
        )
        materias_filtradas = filtrar_materias(materias_brutas)
    except Exception as e:
        logger.error(
            f"Pipeline falhou para {fonte_codigo} (chave {chave}): {e}"
        )
        return []

    classificadas = []
    for materia in materias_filtradas:
        try:
            m_classif = classificar_materia(materia, cliente)
        except Exception as e:
            logger.warning(
                f"Classificação falhou para matéria {materia.tipo}: {e}"
            )
            continue
        # Defesa em profundidade (incidente 2026-06-10, ECA art. 143):
        # filtro determinístico de termos sensíveis DEPOIS do RLM e ANTES
        # de qualquer renderização — não depende do classificador acertar.
        m_final = aplicar_filtro_sensivel(m_classif)
        if m_final is not m_classif:
            logger.warning(
                f"Filtro sensível despublicou matéria {materia.tipo} "
                f"(proteção a menores)"
            )
        classificadas.append(m_final)
    return classificadas


def _processar_fonte(
    fonte_codigo: str,
    data_alvo: date,
    r2: R2Client,
    cliente: ClienteAnthropic,
) -> list[Materia]:
    """Caminho diário: coleta inline (com discover) e delega a processar_chave."""
    chave = coletar_dia(fonte_codigo, data_alvo, r2)
    if chave is None:
        logger.warning(f"Coleta falhou para {fonte_codigo} em {data_alvo}")
        return []
    return processar_chave(chave, fonte_codigo, r2, cliente)


def gerar_jornal_diario(
    data_edicao: date,
    fontes: list[str] | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Orquestra pipeline editorial completo, salva HTML e retorna Path."""
    if data_edicao > date.today():
        raise ValueError(
            f"data_edicao {data_edicao} é futura — não pode ser processada"
        )

    if fontes is None:
        fontes = list(FONTES_VALIDAS)

    for f in fontes:
        if f not in FONTES_VALIDAS:
            raise ValueError(
                f"fonte '{f}' inválida. Use uma de {FONTES_VALIDAS}"
            )

    if output_dir is None:
        output_dir = OUTPUT_DIR_DEFAULT
    output_dir.mkdir(parents=True, exist_ok=True)

    r2 = R2Client.from_env()
    cliente = ClienteAnthropic(extended_thinking=False)

    todas_materias: list[Materia] = []
    for fonte in fontes:
        logger.info(f"Processando {fonte} para {data_edicao}...")
        mats = _processar_fonte(fonte, data_edicao, r2, cliente)
        todas_materias.extend(mats)
        logger.info(f"  {fonte}: {len(mats)} matérias classificadas")

    url_jornal = r2.url_publica(f"jornal/{data_edicao.isoformat()}.html")
    html = renderizar_jornal(todas_materias, data_edicao, url_canonica=url_jornal)

    output_path = output_dir / f"{data_edicao.isoformat()}.html"
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"Jornal salvo em {output_path}")

    # Sidecar JSON (Ciclo 11.4): persiste matérias relevantes em disco para que
    # o passo seguinte (scripts.publicar) possa subi-lo ao R2 sem reprocessar.
    sidecar = montar_sidecar(todas_materias, data_edicao, url_jornal)
    sidecar_path = output_path.with_suffix(".json")
    sidecar_path.write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    logger.info(f"Sidecar salvo em {sidecar_path}")

    return output_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera jornal editorial diário do Observatório Roraima",
    )
    parser.add_argument(
        "--data",
        default="hoje",
        help="Data da edição (ISO yyyy-mm-dd ou 'hoje'). Default: hoje.",
    )
    parser.add_argument(
        "--fonte",
        choices=("MPRR", "TJRR", "todas"),
        default="todas",
        help="Fonte a processar. Default: todas.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR_DEFAULT,
        help=f"Diretório de saída. Default: {OUTPUT_DIR_DEFAULT}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv)

    if args.data == "hoje":
        data_edicao = date.today()
    else:
        data_edicao = date.fromisoformat(args.data)

    if args.fonte == "todas":
        fontes = list(FONTES_VALIDAS)
    else:
        fontes = [args.fonte]

    try:
        output_path = gerar_jornal_diario(
            data_edicao=data_edicao,
            fontes=fontes,
            output_dir=args.output,
        )
        print(f"Jornal gerado: {output_path}")
        return 0
    except Exception as e:
        logger.error(f"Falha ao gerar jornal: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
