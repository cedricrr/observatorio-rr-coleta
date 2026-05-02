"""Descoberta de diários do TJRR (URL determinística por data)."""

from __future__ import annotations

from datetime import date

import requests


BASE = "https://diario.tjrr.jus.br/dpj"
USER_AGENT = (
    "Mozilla/5.0 (ObservatorioRoraima/1.0; "
    "+https://observatoriororaima.org)"
)
TIMEOUT = 15


def discover(data_alvo: date) -> dict | None:
    """Verifica se há diário do TJRR publicado em data_alvo.

    Retorna dict com {url, data_edicao, numero, titulo} se 200,
    None em qualquer outro status ou erro de rede.
    """
    url = f"{BASE}/dpj-{data_alvo.strftime('%Y%m%d')}.pdf"
    try:
        response = requests.head(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    return {
        "url": url,
        "data_edicao": data_alvo.isoformat(),
        "numero": None,
        "titulo": None,
    }
