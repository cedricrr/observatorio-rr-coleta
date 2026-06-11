"""Cache de extração de texto no R2.

Para cada PDF arquivado em `{orgao}/{ano}/{mes}/{data}[-{numero}].pdf`,
grava `texto/{mesma chave}.json` com o texto integral por página — a base
reconstruível do índice de busca (fonte da verdade continua sendo o R2).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import fitz

from scripts.backfill import (
    Checkpoint,
    carregar_checkpoint,
    gerar_relatorio,
    gravar_checkpoint,
    ja_processado,
    marcar_processado,
)
from scripts.baixar_pdf import baixar_pdf_do_r2
from scripts.extrair_texto import extrair_paginas
from scripts.r2_client import R2Client

logger = logging.getLogger(__name__)

ORGAOS_VALIDOS = ("mprr", "tjrr", "todas")

VERSAO_SCHEMA = 1

# Páginas com menos de 20 caracteres úteis são tratadas como vazias —
# sinal de PDF escaneado sem camada de texto (não-buscável até haver OCR).
LIMIAR_PAGINA_VAZIA = 20


def chave_texto(chave_pdf: str) -> str:
    """Converte a chave R2 de um PDF na chave do JSON de texto correspondente.

    `mprr/2022/04/2022-04-26-4.pdf` → `texto/mprr/2022/04/2022-04-26-4.json`
    """
    if not chave_pdf.endswith(".pdf"):
        raise ValueError(f"chave de PDF inválida: {chave_pdf!r}")
    return "texto/" + chave_pdf[: -len(".pdf")] + ".json"


def chave_pdf_de_metadados(metadados: dict) -> str:
    """Extrai a chave R2 do PDF a partir do campo url_r2 do JSON de metadados."""
    return urlparse(metadados["url_r2"]).path.lstrip("/")


def montar_documento(metadados: dict, paginas: list[str]) -> dict:
    """Monta o documento de texto (schema versao=1) — contrato com o indexador.

    `metadados` é um JSON de `data/diarios/` (orgao, data_edicao, numero,
    sha256, url_r2); `paginas` vem de `extrair_paginas` (índice 0 = página 1).
    """
    vazias = sum(1 for t in paginas if len(t.strip()) < LIMIAR_PAGINA_VAZIA)
    return {
        "versao": VERSAO_SCHEMA,
        "orgao": metadados["orgao"],
        "data_edicao": metadados["data_edicao"],
        "numero": metadados.get("numero"),
        "chave_pdf": chave_pdf_de_metadados(metadados),
        "sha256_pdf": metadados["sha256"],
        "extraido_em": datetime.now().isoformat(),
        "extrator": f"pymupdf-{fitz.pymupdf_version}",
        "total_paginas": len(paginas),
        "paginas_vazias": vazias,
        "paginas": [{"n": n, "texto": t} for n, t in enumerate(paginas, start=1)],
    }


def extrair_e_gravar(
    metadados: dict, r2: R2Client, sobrescrever: bool = False,
) -> tuple[str, str | None]:
    """Extrai o texto do PDF de uma edição e grava o JSON em texto/ no R2.

    Retorna (status, detalhes) no vocabulário do checkpoint de backfill:
    "pulado_dedupe" se o JSON já existe (a menos de `sobrescrever`),
    "sucesso" após upload. O objeto é imutável (sem Cache-Control);
    regeneração futura é via sobrescrever + bump de VERSAO_SCHEMA.
    """
    chave_pdf = chave_pdf_de_metadados(metadados)
    chave = chave_texto(chave_pdf)

    if not sobrescrever and r2.existe(chave):
        return "pulado_dedupe", None

    pdf_bytes = baixar_pdf_do_r2(chave_pdf, r2)
    paginas = extrair_paginas(pdf_bytes)
    documento = montar_documento(metadados, paginas)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    ) as tmp:
        json.dump(documento, tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    try:
        r2.upload(
            tmp_path,
            chave,
            metadados={"data-edicao": documento["data_edicao"]},
            content_type="application/json",
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    detalhes = (
        f"{documento['total_paginas']} paginas, "
        f"{documento['paginas_vazias']} vazias"
    )
    logger.info(f"Texto gravado: {chave} ({detalhes})")
    return "sucesso", detalhes


def listar_metadados(diarios_dir: Path, orgao: str) -> list[dict]:
    """Lê os JSONs de data/diarios/ (filtrando por órgão) em ordem estável."""
    if orgao not in ORGAOS_VALIDOS:
        raise ValueError(f"orgao inválido: {orgao!r}")
    orgaos = ["mprr", "tjrr"] if orgao == "todas" else [orgao]
    metadados: list[dict] = []
    for o in orgaos:
        pasta = diarios_dir / o
        if not pasta.is_dir():
            continue
        for caminho in sorted(pasta.glob("*.json")):
            metadados.append(json.loads(caminho.read_text(encoding="utf-8")))
    return metadados


def backfill_texto(
    metadados_lista: list[dict],
    r2: R2Client | None,
    checkpoint: Checkpoint,
    pausa: float,
    dry_run: bool = False,
    sobrescrever: bool = False,
    caminho_checkpoint: Path | None = None,
) -> Checkpoint:
    """Extrai e grava o texto de cada edição, com checkpoint retomável.

    Mesmas garantias do backfill de coleta: persiste após cada item e em
    try/finally; `item_id` é a chave R2 do PDF; dry-run não toca o R2.
    """
    try:
        for metadados in metadados_lista:
            item_id = chave_pdf_de_metadados(metadados)
            if ja_processado(checkpoint, item_id):
                continue
            if dry_run:
                marcar_processado(checkpoint, item_id, "pulado_dedupe")
            else:
                try:
                    status, detalhes = extrair_e_gravar(
                        metadados, r2, sobrescrever=sobrescrever,
                    )
                    marcar_processado(checkpoint, item_id, status, detalhes)
                except Exception as e:
                    marcar_processado(checkpoint, item_id, "erro", str(e))
            if caminho_checkpoint is not None:
                gravar_checkpoint(checkpoint, caminho_checkpoint)
            if pausa > 0:
                time.sleep(pausa)
    finally:
        if caminho_checkpoint is not None:
            gravar_checkpoint(checkpoint, caminho_checkpoint)
    return checkpoint


def main(argv: list[str] | None = None) -> int:
    """Entry point CLI: python -m scripts.cache_texto --backfill [...]"""
    parser = argparse.ArgumentParser(
        description="Cache de extração de texto dos diários no R2 (texto/)",
    )
    parser.add_argument("--backfill", action="store_true", required=True)
    parser.add_argument("--orgao", choices=ORGAOS_VALIDOS, default="todas")
    parser.add_argument("--retomar", action="store_true")
    parser.add_argument("--sobrescrever", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pausa", type=float, default=0.0)
    parser.add_argument("--diarios-dir", default="data/diarios")
    parser.add_argument("--checkpoint-dir", default="data/backfill")

    args = parser.parse_args(argv)

    escopo = f"texto-{args.orgao}"
    caminho_ckpt = Path(args.checkpoint_dir) / f"{escopo}.json"

    checkpoint = None
    if args.retomar:
        checkpoint = carregar_checkpoint(caminho_ckpt)

    if checkpoint is None:
        agora = datetime.now().isoformat()
        checkpoint = Checkpoint(
            escopo=escopo,
            iniciado_em=agora,
            atualizado_em=agora,
            itens=[],
            config={
                "orgao": args.orgao,
                "pausa": args.pausa,
                "dry_run": args.dry_run,
                "sobrescrever": args.sobrescrever,
            },
        )

    metadados_lista = listar_metadados(Path(args.diarios_dir), args.orgao)
    r2 = None if args.dry_run else R2Client.from_env()

    checkpoint = backfill_texto(
        metadados_lista, r2, checkpoint, args.pausa,
        dry_run=args.dry_run,
        sobrescrever=args.sobrescrever,
        caminho_checkpoint=caminho_ckpt,
    )

    print(gerar_relatorio(checkpoint))

    houve_erro = any(item["status"] == "erro" for item in checkpoint.itens)
    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
