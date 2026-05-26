"""Backfill de publicação (Ciclo 10.6).

Gera e publica jornais editoriais retroativos a partir das chaves R2 já
coletadas em data/diarios/, SEM re-discover nos portais (que falharia para
datas antigas e geraria jornal vazio mesmo com o PDF no R2). Idempotente:
pula datas cujo jornal já existe no R2.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from scripts.cliente_anthropic import ClienteAnthropic
from scripts.jornal_diario import processar_chave
from scripts.publicar import PREFIXO_R2, publicar_jornal
from scripts.r2_client import R2Client
from scripts.renderizar import renderizar_jornal
from scripts.segmentar import Materia

# Diretório de origem → código de fonte aceito por processar_chave/segmentar.
_FONTE_POR_DIR = {"mprr": "MPRR", "tjrr": "TJRR"}
_RE_DATA_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def chave_jornal(data: date) -> str:
    """Chave R2 do jornal de uma data: jornal/AAAA-MM-DD.html."""
    return f"{PREFIXO_R2}{data.isoformat()}.html"


def mapear_chaves(diarios_dir: Path) -> dict[date, dict[str, str]]:
    """Varre data/diarios/{fonte}/*.json e devolve {data: {FONTE: chave_r2}}.

    A chave R2 do PDF é extraída de `url_r2` (mesma lógica do coletar_dia).
    JSON sem `url_r2` ou com nome fora do padrão de data é ignorado.
    """
    mapa: dict[date, dict[str, str]] = {}
    if not diarios_dir.exists():
        return mapa

    for fonte_dir in sorted(diarios_dir.iterdir()):
        if not fonte_dir.is_dir():
            continue
        fonte = _FONTE_POR_DIR.get(fonte_dir.name)
        if fonte is None:
            continue
        for json_path in fonte_dir.glob("*.json"):
            m = _RE_DATA_ISO.match(json_path.stem)
            if not m:
                continue
            try:
                dados = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            url_r2 = dados.get("url_r2")
            if not url_r2:
                continue
            chave = urlparse(url_r2).path.lstrip("/")
            data_edicao = date.fromisoformat(m.group(1))
            mapa.setdefault(data_edicao, {})[fonte] = chave
    return mapa


def processar_data(
    data: date,
    chaves_por_fonte: dict[str, str],
    r2: R2Client,
    cliente: ClienteAnthropic,
    output_dir: Path,
) -> tuple[str, int]:
    """Gera e publica o jornal de uma data a partir de chaves conhecidas.

    Pula (sem reprocessar) se o jornal já existe no R2. Retorna
    (status, n_materias): status ∈ {"pulado_dedupe", "sucesso"}. Exceções
    de geração/publicação propagam para o orquestrador marcar "erro".
    """
    if r2.existe(chave_jornal(data)):
        return ("pulado_dedupe", 0)

    materias: list[Materia] = []
    for fonte, chave in sorted(chaves_por_fonte.items()):
        materias.extend(processar_chave(chave, fonte, r2, cliente))

    html = renderizar_jornal(materias, data)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{data.isoformat()}.html"
    output_path.write_text(html, encoding="utf-8")
    publicar_jornal(output_path, r2, data)

    return ("sucesso", len(materias))
