"""Orquestrador do jornal editorial diário.

Pipeline ponta a ponta: garante PDF no R2 (via coletor inline se
necessário), processa pelos estágios 8.1-8.7, renderiza HTML
consolidado de todas as fontes do dia.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

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

logger = logging.getLogger(__name__)

FONTES_VALIDAS = ("MPRR", "TJRR")
OUTPUT_DIR_DEFAULT = Path("/tmp/observatorio-roraima")


def coletar_dia(fonte_codigo: str, data_alvo: date, r2: R2Client) -> bool:
    """Wrapper sobre processar_fonte adaptando assinatura.

    Recebe string ('MPRR' ou 'TJRR') e devolve bool indicando sucesso.
    Internamente resolve a string para objeto Fonte e chama
    processar_fonte do scripts.coletar.
    """
    try:
        fonte_obj = get_fonte(fonte_codigo.lower())
        resultado = processar_fonte(fonte_obj, data_alvo, r2)
        return resultado is not None
    except Exception as e:
        logger.warning(
            f"Coleta de {fonte_codigo} para {data_alvo} falhou: {e}"
        )
        return False


def _construir_chave_r2(fonte_codigo: str, data_alvo: date) -> str:
    return (
        f"{fonte_codigo.lower()}/{data_alvo.year}/"
        f"{data_alvo.month:02d}/{data_alvo.isoformat()}.pdf"
    )


def _processar_fonte(
    fonte_codigo: str,
    data_alvo: date,
    r2: R2Client,
    cliente: ClienteAnthropic,
) -> list[Materia]:
    """Pipeline completo para 1 fonte. Retorna matérias classificadas."""
    chave = _construir_chave_r2(fonte_codigo, data_alvo)

    if not r2.existe(chave):
        logger.info(f"PDF {chave} não no R2, disparando coletor...")
        if not coletar_dia(fonte_codigo, data_alvo, r2):
            logger.warning(f"Coleta falhou para {fonte_codigo}")
            return []
        if not r2.existe(chave):
            logger.warning(
                f"PDF {chave} ainda não disponível após coleta"
            )
            return []

    try:
        pdf_bytes = baixar_pdf_do_r2(chave, r2)
        markdown = pdf_para_markdown(pdf_bytes)
        pdf_url = f"https://example.com/{chave}"
        materias_brutas = segmentar_materias(
            markdown, fonte_codigo, pdf_url,
        )
        materias_filtradas = filtrar_materias(materias_brutas)
    except Exception as e:
        logger.error(f"Pipeline falhou para {fonte_codigo}: {e}")
        return []

    classificadas = []
    for materia in materias_filtradas:
        try:
            m_classif = classificar_materia(materia, cliente)
            classificadas.append(m_classif)
        except Exception as e:
            logger.warning(
                f"Classificação falhou para matéria {materia.tipo}: {e}"
            )
            continue
    return classificadas


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

    html = renderizar_jornal(todas_materias, data_edicao)

    output_path = output_dir / f"{data_edicao.isoformat()}.html"
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"Jornal salvo em {output_path}")

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
