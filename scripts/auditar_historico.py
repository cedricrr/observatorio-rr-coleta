"""Auditoria histórica de matérias publicadas — proteção a menores.

Fase 4 do incidente 2026-06-10 (ECA art. 143 — ver
docs/incidentes/2026-06-10-protecao-menores.md). Varre TODOS os sidecars
publicados (`jornal/AAAA-MM-DD.json` no R2 — fonte da verdade do que está
no ar, mesma filosofia do sitemap/dedupe), aplica `casar_termo_sensivel`
(Fase 3) a cada matéria e gera relatório.

SOMENTE LEITURA: este script não modifica nada — nem R2, nem git. O
relatório completo (com manchetes, que podem conter conteúdo sensível) é
salvo em data/incidentes/ (gitignored); a decisão de despublicar é do
editor, caso a caso ou em lote.

Uso:
    python -m scripts.auditar_historico
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.r2_client import R2Client
from scripts.segmentar import Materia
from scripts.validador_sensivel import casar_termo_sensivel

logger = logging.getLogger(__name__)

AUDITORIA_DIR = Path("data/incidentes")
_RE_CHAVE_SIDECAR = re.compile(r"^jornal/(\d{4}-\d{2}-\d{2})\.json$")


def _materia_de_dict(d: dict) -> Materia:
    """Reconstrói Materia a partir do dict do sidecar (sem `texto`).

    O sidecar não persiste o markdown bruto, então a auditoria avalia a
    superfície PUBLICADA (manchete/resumo/tags) — exatamente o que expõe
    a vítima. O replay do incidente real (Fase 3) confirmou que essa
    superfície é suficiente para casar os termos.
    """
    return Materia(
        orgao=d.get("orgao") or "",
        tipo=d.get("tipo") or "DESCONHECIDO",
        texto="",
        pdf_url=d.get("pdf_url") or "",
        pagina=d.get("pagina"),
        categoria=d.get("categoria"),
        manchete=d.get("manchete"),
        resumo=d.get("resumo"),
        valor_rs=d.get("valor_rs"),
        tags=d.get("tags") or [],
    )


def auditar_sidecar(sidecar: dict) -> list[dict]:
    """Aplica o filtro sensível às matérias de um sidecar (sem modificar).

    Retorna um achado por matéria que casou: data, órgão, manchete
    original e o termo (nome da regra) que casou.
    """
    achados: list[dict] = []
    for m in sidecar.get("materias", []):
        termo = casar_termo_sensivel(_materia_de_dict(m))
        if termo is not None:
            achados.append({
                "data_edicao": sidecar.get("data_edicao"),
                "orgao": m.get("orgao"),
                "manchete": m.get("manchete"),
                "termo": termo,
            })
    return achados


def auditar_historico(r2: R2Client) -> dict:
    """Varre todos os sidecars do R2 e agrega o relatório da auditoria."""
    chaves = sorted(
        c for c in r2.listar("jornal/") if _RE_CHAVE_SIDECAR.match(c)
    )
    logger.info(f"{len(chaves)} sidecars de edição encontrados no R2")

    total_materias = 0
    achados: list[dict] = []
    erros: list[str] = []
    for i, chave in enumerate(chaves, 1):
        try:
            sidecar = json.loads(r2.download_bytes(chave).decode("utf-8"))
        except Exception as e:
            logger.warning(f"Falha ao baixar/parsear {chave}: {e}")
            erros.append(chave)
            continue
        total_materias += len(sidecar.get("materias", []))
        achados.extend(auditar_sidecar(sidecar))
        if i % 100 == 0:
            logger.info(f"  {i}/{len(chaves)} sidecars auditados...")

    return {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "total_edicoes_auditadas": len(chaves) - len(erros),
        "total_materias_auditadas": total_materias,
        "total_casaram_filtro": len(achados),
        "sidecars_com_erro": erros,
        "achados": achados,
    }


def _imprimir_relatorio(relatorio: dict) -> None:
    print()
    print("=" * 72)
    print("AUDITORIA HISTÓRICA — proteção a menores (ECA art. 143)")
    print("=" * 72)
    print(f"Edições auditadas:   {relatorio['total_edicoes_auditadas']}")
    print(f"Matérias auditadas:  {relatorio['total_materias_auditadas']}")
    print(f"Casaram com filtro:  {relatorio['total_casaram_filtro']}")
    if relatorio["sidecars_com_erro"]:
        print(f"Sidecars com erro:   {len(relatorio['sidecars_com_erro'])} "
              f"{relatorio['sidecars_com_erro']}")
    print("-" * 72)
    for a in relatorio["achados"]:
        print(f"{a['data_edicao']}  [{a['orgao']}]  termo: {a['termo']}")
        print(f"    {a['manchete']}")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    )
    argparse.ArgumentParser(
        description="Audita matérias publicadas (somente leitura)",
    ).parse_args(argv)

    r2 = R2Client.from_env()
    relatorio = auditar_historico(r2)

    AUDITORIA_DIR.mkdir(parents=True, exist_ok=True)
    destino = AUDITORIA_DIR / (
        "auditoria-historico-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    destino.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    _imprimir_relatorio(relatorio)
    print(f"Relatório salvo em {destino} (gitignored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
