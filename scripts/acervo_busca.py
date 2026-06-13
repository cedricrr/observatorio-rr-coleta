"""Contagem de ocorrências no acervo via API de busca (Sessão 13.3).

Consultada no BUILD da edição para o bloco "Este assunto no acervo".
Resiliência na linha do pipeline editorial: qualquer falha vira None e
o bloco é omitido — nunca quebra o build. O cache (dict por execução)
evita repetir requests para o mesmo termo e absorve o rate limit do
/buscar (30/min); falha não é cacheada para o próximo build tentar
de novo.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 10


def contar_diarios(termo: str, api_url: str, cache: dict[str, int]) -> int | None:
    """Total de diários que citam o termo, ou None em qualquer falha."""
    if termo in cache:
        return cache[termo]
    try:
        resposta = requests.post(
            f"{api_url.rstrip('/')}/buscar",
            json={"q": termo},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as e:
        logger.warning("contagem no acervo falhou para %r: %s", termo, e)
        return None
    if resposta.status_code != 200:
        logger.warning(
            "contagem no acervo para %r retornou HTTP %s", termo, resposta.status_code
        )
        return None
    try:
        total = int(resposta.json()["total_diarios"])
    except (ValueError, KeyError, TypeError):
        return None
    cache[termo] = total
    return total
