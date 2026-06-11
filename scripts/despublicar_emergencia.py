"""Despublicação de emergência de matérias já publicadas no R2.

Criado no incidente de 2026-06-10 (proteção a menores, ECA art. 143 —
ver docs/incidentes/2026-06-10-protecao-menores.md). Remove matérias do
sidecar público de uma edição, re-renderiza o HTML da edição a partir do
próprio sidecar (sem reprocessar via RLM) e regenera o índice da home.

A matéria removida NÃO é apagada do histórico: uma cópia de auditoria do
sidecar original e das matérias removidas (marcadas relevante=False) é
gravada em data/incidentes/ — local e gitignored, nunca no R2 público.

Uso:
    python -m scripts.despublicar_emergencia --data 2026-05-29 \
        --casar "estupro de vulnerável" --casar "adolescente" [--dry-run]

`--casar` é um regex (case-insensitive) testado contra manchete, resumo e
tags de cada matéria do sidecar; qualquer match despublica a matéria.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.publicar import (
    baixar_sidecar,
    gerar_indice,
    publicar_indice,
    publicar_jornal,
    publicar_sidecar,
)
from scripts.r2_client import R2Client
from scripts.renderizar import renderizar_jornal
from scripts.segmentar import Materia

logger = logging.getLogger(__name__)

AUDITORIA_DIR = Path("data/incidentes")


def _materia_casa(materia: dict, padroes: list[re.Pattern]) -> str | None:
    """Retorna o pattern que casou com manchete/resumo/tags, ou None."""
    campos = [
        materia.get("manchete") or "",
        materia.get("resumo") or "",
        " ".join(materia.get("tags") or []),
    ]
    texto = "\n".join(campos)
    for padrao in padroes:
        if padrao.search(texto):
            return padrao.pattern
    return None


def _dict_para_materia(d: dict) -> Materia:
    """Reconstrói Materia a partir do dict do sidecar (sem `texto`)."""
    return Materia(
        orgao=d["orgao"],
        tipo=d.get("tipo") or "DESCONHECIDO",
        texto="",
        pdf_url=d.get("pdf_url") or "",
        pagina=d.get("pagina"),
        categoria=d.get("categoria"),
        manchete=d.get("manchete"),
        resumo=d.get("resumo"),
        valor_rs=d.get("valor_rs"),
        tags=d.get("tags") or [],
        relevante=True,
    )


def despublicar(
    data_edicao: date,
    padroes_brutos: list[str],
    dry_run: bool = False,
) -> int:
    """Despublica matérias da edição cujo conteúdo casa com os padrões.

    Retorna o número de matérias removidas (0 = nada a fazer).
    """
    padroes = [re.compile(p, re.IGNORECASE) for p in padroes_brutos]
    r2 = R2Client.from_env()

    sidecar = baixar_sidecar(data_edicao, r2)
    if sidecar is None:
        raise RuntimeError(
            f"Sidecar jornal/{data_edicao.isoformat()}.json não existe no R2"
        )

    mantidas: list[dict] = []
    removidas: list[dict] = []
    for m in sidecar["materias"]:
        motivo = _materia_casa(m, padroes)
        if motivo is None:
            mantidas.append(m)
        else:
            removidas.append({**m, "relevante": False, "padrao_casado": motivo})
            logger.info(f"DESPUBLICAR: {m.get('manchete')!r} (casou {motivo!r})")

    if not removidas:
        logger.info("Nenhuma matéria casou com os padrões — nada a fazer.")
        return 0

    # Auditoria local (gitignored): sidecar original + matérias removidas.
    AUDITORIA_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDITORIA_DIR / (
        f"{data_edicao.isoformat()}-despublicacao-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    audit_path.write_text(
        json.dumps(
            {
                "incidente": "protecao-menores ECA art. 143",
                "executado_em_utc": datetime.now(timezone.utc).isoformat(),
                "data_edicao": data_edicao.isoformat(),
                "padroes": padroes_brutos,
                "sidecar_original": sidecar,
                "materias_removidas": removidas,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"Auditoria gravada em {audit_path}")

    if dry_run:
        logger.info(f"[dry-run] removeria {len(removidas)} matéria(s).")
        return len(removidas)

    # 1. Sidecar público sem as matérias despublicadas.
    sidecar_novo = {
        **sidecar,
        "total_relevantes": len(mantidas),
        "materias": mantidas,
    }
    publicar_sidecar(sidecar_novo, r2, data_edicao)

    # 2. HTML da edição re-renderizado a partir do sidecar (sem RLM).
    materias = [_dict_para_materia(m) for m in mantidas]
    html = renderizar_jornal(
        materias, data_edicao, url_canonica=sidecar.get("url_jornal"),
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)
    try:
        publicar_jornal(tmp_path, r2, data_edicao)
    finally:
        tmp_path.unlink(missing_ok=True)

    # 3. Índice da home re-agregado dos sidecars (já sem as removidas).
    html_indice = gerar_indice(public_domain=r2.public_domain, r2=r2)
    publicar_indice(html_indice, r2)

    logger.info(f"{len(removidas)} matéria(s) despublicada(s).")
    return len(removidas)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Despublica matérias de uma edição já publicada no R2",
    )
    parser.add_argument("--data", required=True, help="Data da edição (ISO)")
    parser.add_argument(
        "--casar", action="append", required=True,
        help="Regex (case-insensitive) contra manchete/resumo/tags; repetível.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv)
    try:
        despublicar(date.fromisoformat(args.data), args.casar, args.dry_run)
        return 0
    except Exception as e:
        logger.error(f"Falha na despublicação: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
