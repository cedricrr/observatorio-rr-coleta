"""Testes de scripts/acervo_busca.py (Sessão 13.3).

Contagem de diários que citam um termo, consultada à API de busca no
BUILD da edição. Resiliência na linha do pipeline editorial: qualquer
falha vira None e o bloco é omitido — nunca quebra o build.
"""

from unittest import mock

import requests

from scripts.acervo_busca import contar_diarios


def _resposta(total: int) -> mock.MagicMock:
    resposta = mock.MagicMock()
    resposta.status_code = 200
    resposta.json.return_value = {
        "total_diarios": total,
        "total_ocorrencias": total * 3,
        "parcial": True,
        "resultados": [],
    }
    return resposta


def test_retorna_total_de_diarios_da_api():
    with mock.patch("scripts.acervo_busca.requests.post") as post:
        post.return_value = _resposta(12)

        total = contar_diarios("Empresa XYZ", "https://api.example", cache={})

    assert total == 12
    args, kwargs = post.call_args
    assert args[0] == "https://api.example/buscar"
    assert kwargs["json"]["q"] == "Empresa XYZ"


def test_falha_de_rede_retorna_none():
    with mock.patch("scripts.acervo_busca.requests.post") as post:
        post.side_effect = requests.ConnectionError("recusada")

        total = contar_diarios("Empresa XYZ", "https://api.example", cache={})

    assert total is None


def test_status_nao_200_retorna_none():
    with mock.patch("scripts.acervo_busca.requests.post") as post:
        post.return_value = mock.MagicMock(status_code=502)

        total = contar_diarios("Empresa XYZ", "https://api.example", cache={})

    assert total is None


def test_cache_evita_segunda_chamada():
    cache: dict = {}
    with mock.patch("scripts.acervo_busca.requests.post") as post:
        post.return_value = _resposta(7)

        primeiro = contar_diarios("Empresa XYZ", "https://api.example", cache=cache)
        segundo = contar_diarios("Empresa XYZ", "https://api.example", cache=cache)

    assert primeiro == segundo == 7
    assert post.call_count == 1


def test_falha_nao_e_cacheada():
    # próximo build tenta de novo — só sucesso entra no cache
    cache: dict = {}
    with mock.patch("scripts.acervo_busca.requests.post") as post:
        post.side_effect = [requests.ConnectionError("x"), _resposta(3)]

        assert contar_diarios("Empresa XYZ", "https://api.example", cache=cache) is None
        assert contar_diarios("Empresa XYZ", "https://api.example", cache=cache) == 3

    assert post.call_count == 2
