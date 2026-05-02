"""Coletor de diários oficiais — funções core."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import requests

from scripts.config import Fonte


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
