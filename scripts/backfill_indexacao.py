"""Backfill de indexação: textos do R2 (texto/) → POST /indexar da API de busca.

A indexação passa SEMPRE pela API pública autenticada — o Solr nunca é
exposto, e este caminho é o mesmo do fluxo diário (indexar_diaria).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from scripts.backfill import (
    Checkpoint,
    carregar_checkpoint,
    gerar_relatorio,
    gravar_checkpoint,
    ja_processado,
    marcar_processado,
)
from scripts.r2_client import R2Client

TIMEOUT_SEGUNDOS = 120
TENTATIVAS = 2  # 1 retry: edições TJRR grandes podem dar timeout esporádico

PREFIXO_TEXTO = "texto/"


def postar_documento(api_url: str, token: str, documento_bytes: bytes) -> dict:
    """POST do JSON de texto ao /indexar, com 1 retry. Retorna o JSON da resposta."""
    url = f"{api_url.rstrip('/')}/indexar"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    ultima_falha: requests.RequestException | None = None
    for _ in range(TENTATIVAS):
        try:
            resposta = requests.post(
                url, data=documento_bytes, headers=headers, timeout=TIMEOUT_SEGUNDOS,
            )
            resposta.raise_for_status()
            return resposta.json()
        except requests.RequestException as e:
            ultima_falha = e
    raise ultima_falha


def indexar_chave(
    chave: str, r2: R2Client, api_url: str, token: str,
) -> tuple[str, str | None]:
    """Baixa um JSON de texto do R2 e envia ao /indexar."""
    corpo = r2.download_bytes(chave)
    resposta = postar_documento(api_url, token, corpo)
    return "sucesso", f"{resposta.get('indexadas', '?')} paginas indexadas"


def backfill_indexacao(
    chaves: list[str],
    r2: R2Client,
    api_url: str,
    token: str,
    checkpoint: Checkpoint,
    pausa: float,
    dry_run: bool = False,
    caminho_checkpoint: Path | None = None,
) -> Checkpoint:
    """Indexa cada chave de texto, com checkpoint retomável.

    Mesmas garantias dos demais backfills: persiste após cada item e em
    try/finally; erro em um item não para o resto.
    """
    try:
        for chave in chaves:
            if ja_processado(checkpoint, chave):
                continue
            if dry_run:
                marcar_processado(checkpoint, chave, "pulado_dedupe")
            else:
                try:
                    status, detalhes = indexar_chave(chave, r2, api_url, token)
                    marcar_processado(checkpoint, chave, status, detalhes)
                except Exception as e:
                    marcar_processado(checkpoint, chave, "erro", str(e))
            if caminho_checkpoint is not None:
                gravar_checkpoint(checkpoint, caminho_checkpoint)
            if pausa > 0:
                time.sleep(pausa)
    finally:
        if caminho_checkpoint is not None:
            gravar_checkpoint(checkpoint, caminho_checkpoint)
    return checkpoint


def main(argv: list[str] | None = None) -> int:
    """Entry point CLI: python -m scripts.backfill_indexacao [...]"""
    parser = argparse.ArgumentParser(
        description="Backfill de indexação: texto/ no R2 → POST /indexar",
    )
    parser.add_argument("--retomar", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pausa", type=float, default=0.5)
    parser.add_argument("--checkpoint-dir", default="data/backfill")

    args = parser.parse_args(argv)

    load_dotenv(Path.cwd() / ".env")
    api_url = os.environ.get("SEARCH_API_URL")
    token = os.environ.get("SEARCH_API_TOKEN")
    if not args.dry_run and (not api_url or not token):
        print(
            "SEARCH_API_URL e SEARCH_API_TOKEN são obrigatórias (defina no .env)",
            file=sys.stderr,
        )
        return 2

    escopo = "indexacao"
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
            config={"pausa": args.pausa, "dry_run": args.dry_run},
        )

    r2 = R2Client.from_env()
    chaves = r2.listar(PREFIXO_TEXTO)

    checkpoint = backfill_indexacao(
        chaves, r2, api_url, token, checkpoint, args.pausa,
        dry_run=args.dry_run, caminho_checkpoint=caminho_ckpt,
    )

    print(gerar_relatorio(checkpoint))

    houve_erro = any(item["status"] == "erro" for item in checkpoint.itens)
    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
