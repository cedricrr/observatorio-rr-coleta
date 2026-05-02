"""Descoberta de diários do MPRR (POST + CSRF + parsing de 12 JSONs)."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


PORTAL = "https://www.mprr.mp.br"
LISTAGEM = f"{PORTAL}/servicos/diario"
USER_AGENT = (
    "Mozilla/5.0 (ObservatorioRoraima/1.0; "
    "+https://observatoriororaima.org)"
)
TIMEOUT = 30
PADRAO_NUMERO = re.compile(
    r"n[º°.]?\s*(\d+)\s*[-–]?\s*\d{4}", re.IGNORECASE
)


# --- privadas ---

def _get_session_with_csrf() -> tuple[requests.Session, str]:
    """Cria sessão com User-Agent e extrai o CSRF token da listagem."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    response = session.get(LISTAGEM, timeout=TIMEOUT)
    soup = BeautifulSoup(response.text, "html.parser")
    meta = soup.find("meta", attrs={"name": "csrf-token"})
    if not meta or not meta.get("content"):
        raise RuntimeError("CSRF token não encontrado na listagem do MPRR")
    return session, meta["content"]


def _fetch_year_html(year: int) -> str:
    """POST com CSRF + ano; devolve o HTML com os JSONs embutidos."""
    session, token = _get_session_with_csrf()
    response = session.post(
        LISTAGEM,
        data={"_token": token, "ano": str(year)},
        timeout=TIMEOUT,
    )
    return response.text


def _extract_month_jsons(html: str) -> list[dict]:
    """Extrai dados1..dados12 do HTML, concatena e ordena por start."""
    todos: list[dict] = []
    for mes in range(1, 13):
        regex = re.compile(rf"var\s+dados{mes}\s*=\s*(\[.*?\]);", re.DOTALL)
        match = regex.search(html)
        if not match:
            continue
        try:
            todos.extend(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    todos.sort(key=lambda d: d.get("start", ""))
    return todos


def _parse_item(raw: dict) -> dict | None:
    """Normaliza item bruto. data_edicao SEMPRE vem do start."""
    url_rel = raw.get("url")
    start = raw.get("start")
    if not url_rel or not start:
        return None
    titulo = raw.get("title")
    match = PADRAO_NUMERO.search(titulo or "")
    numero = int(match.group(1)) if match else None
    return {
        "url": urljoin(PORTAL, url_rel),
        "numero": numero,
        "data_edicao": start,
        "titulo": titulo,
    }


# --- públicas ---

def list_year(year: int) -> list[dict]:
    """Lista todos os diários do MPRR em um ano, ordenados por data."""
    html = _fetch_year_html(year)
    brutos = _extract_month_jsons(html)
    return [it for it in (_parse_item(b) for b in brutos) if it is not None]


def discover(data_alvo: date) -> dict | None:
    """Encontra o diário do MPRR em uma data específica; None se não existe."""
    try:
        items = list_year(data_alvo.year)
    except requests.RequestException:
        return None
    iso = data_alvo.isoformat()
    for item in items:
        if item["data_edicao"] == iso:
            return item
    return None


def list_years(years: Iterable[int]) -> list[dict]:
    """Conveniência multi-ano para backfill. Tolera falha em ano específico."""
    todos: list[dict] = []
    for ano in years:
        try:
            todos.extend(list_year(ano))
        except requests.RequestException:
            continue
    return todos
