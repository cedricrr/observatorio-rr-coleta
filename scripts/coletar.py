"""Coletor de diários oficiais — funções core e orquestração."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

from scripts.config import FONTES, Fonte, get_fonte
from scripts.r2_client import R2Client


USER_AGENT = (
    "Mozilla/5.0 (ObservatorioRoraima/1.0; "
    "+https://observatoriororaima.org)"
)
TIMEOUT_DOWNLOAD = 60
TIMEOUT_WAYBACK = 30
CHUNK_SIZE = 65536  # 64 KB


def baixar_pdf(
    url: str,
    destino: Path,
    timeout: int = TIMEOUT_DOWNLOAD,
) -> tuple[str, int]:
    """Baixa o PDF em streaming, grava em destino, retorna (sha256_hex, tamanho)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256()
    tamanho = 0
    with requests.get(
        url,
        stream=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as response:
        response.raise_for_status()
        with destino.open("wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                f.write(chunk)
                sha256.update(chunk)
                tamanho += len(chunk)
    return sha256.hexdigest(), tamanho


def submeter_wayback(url: str, timeout: int = TIMEOUT_WAYBACK) -> str | None:
    """Submete URL ao Wayback Machine; retorna URL do snapshot ou None em qualquer erro."""
    try:
        response = requests.get(
            f"https://web.archive.org/save/{url}",
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    location = response.headers.get("Content-Location")
    if not location:
        return None
    return f"https://web.archive.org{location}"


def gravar_metadados(meta: dict, raiz: Path = Path("data/diarios")) -> Path:
    """Escreve metadados em <raiz>/<orgao>/<data>[-<numero>].json. Retorna o Path."""
    orgao = meta["orgao"]
    data_edicao = meta["data_edicao"]
    numero = meta.get("numero")
    nome = f"{data_edicao}-{numero}.json" if numero else f"{data_edicao}.json"
    caminho = raiz / orgao / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return caminho


def montar_chave_r2(fonte: Fonte, descoberta: dict) -> str:
    """Monta chave R2 no padrão <codigo>/<ano>/<mes>/<yyyy-mm-dd>[-<numero>].pdf."""
    data_edicao = descoberta["data_edicao"]
    parsed = date.fromisoformat(data_edicao)
    numero = descoberta.get("numero")
    sufixo = f"-{numero}" if numero else ""
    return f"{fonte.codigo}/{parsed.year:04d}/{parsed.month:02d}/{data_edicao}{sufixo}.pdf"


def processar_descoberta(
    fonte: Fonte,
    descoberta: dict,
    r2: R2Client,
) -> dict | None:
    """Pipeline de uma descoberta: dedupe via R2, download, upload, wayback, metadata."""
    chave = montar_chave_r2(fonte, descoberta)
    url_original = descoberta["url"]
    data_edicao = descoberta["data_edicao"]
    numero = descoberta.get("numero")

    if r2.existe(chave):
        return {
            "orgao": fonte.codigo,
            "data_edicao": data_edicao,
            "numero": numero,
            "url_original": url_original,
            "url_r2": r2.url_publica(chave),
            "ja_existia": True,
        }

    destino = Path("/tmp") / f"{fonte.codigo}-{data_edicao}.pdf"
    try:
        sha256, tamanho = baixar_pdf(url_original, destino)
    except requests.RequestException as e:
        print(f"[{fonte.codigo}] erro baixando {url_original}: {e}", file=sys.stderr)
        return None

    metadados_r2 = {"sha256": sha256, "data-edicao": data_edicao}
    url_r2 = r2.upload(destino, chave, metadados=metadados_r2)
    url_wayback = submeter_wayback(url_original)

    meta = {
        "orgao": fonte.codigo,
        "data_edicao": data_edicao,
        "numero": numero,
        "sha256": sha256,
        "tamanho": tamanho,
        "url_original": url_original,
        "url_r2": url_r2,
        "url_wayback": url_wayback,
        "ja_existia": False,
    }
    gravar_metadados(meta)
    return meta


def processar_fonte(
    fonte: Fonte,
    data_alvo: date,
    r2: R2Client,
) -> dict | None:
    """Descobre o diário da fonte na data e delega o pipeline."""
    mod = importlib.import_module(f"fontes.{fonte.discovery_module}")
    descoberta = mod.discover(data_alvo)
    if descoberta is None:
        return None
    return processar_descoberta(fonte, descoberta, r2)


def main(argv: list[str] | None = None) -> int:
    """Entry point CLI: --data {hoje|ontem|YYYY-MM-DD} --fonte {codigo|todas}."""
    parser = argparse.ArgumentParser(
        description="Coletor de diários oficiais do Observatório Roraima",
    )
    parser.add_argument("--data", default="hoje")
    parser.add_argument(
        "--fonte",
        choices=[f.codigo for f in FONTES] + ["todas"],
        default="todas",
    )
    args = parser.parse_args(argv)

    if args.data == "hoje":
        data_alvo = date.today()
    elif args.data == "ontem":
        data_alvo = date.today() - timedelta(days=1)
    else:
        try:
            data_alvo = date.fromisoformat(args.data)
        except ValueError:
            parser.error(
                f"data inválida: {args.data!r} (use YYYY-MM-DD, 'hoje' ou 'ontem')"
            )

    r2 = R2Client.from_env()
    fontes_a_processar = FONTES if args.fonte == "todas" else [get_fonte(args.fonte)]
    houve_erro = False
    for fonte in fontes_a_processar:
        try:
            processar_fonte(fonte, data_alvo, r2)
        except Exception as e:
            print(f"[{fonte.codigo}] erro: {e}", file=sys.stderr)
            houve_erro = True
    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
