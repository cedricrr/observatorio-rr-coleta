"""Testes do endpoint POST /indexar e da explosão em docs por página."""

import pytest

from app.solr import explodir_documento


def test_explodir_documento_um_doc_por_pagina(documento_texto):
    docs = explodir_documento(documento_texto)

    assert len(docs) == 2
    assert docs[0] == {
        "id": "mprr/2022/04/2022-04-26-4.pdf#1",
        "orgao": "mprr",
        "data_edicao": "2022-04-26T00:00:00Z",
        "numero": 4,
        "pagina": 1,
        "chave_pdf": "mprr/2022/04/2022-04-26-4.pdf",
        "texto": "Portaria nomeando João da Silva",
    }
    assert docs[1]["id"] == "mprr/2022/04/2022-04-26-4.pdf#2"
    assert docs[1]["pagina"] == 2


def test_explodir_documento_omite_numero_nulo(documento_texto):
    documento_texto["numero"] = None

    docs = explodir_documento(documento_texto)

    assert "numero" not in docs[0]


def test_explodir_documento_rejeita_versao_desconhecida(documento_texto):
    documento_texto["versao"] = 2

    with pytest.raises(ValueError):
        explodir_documento(documento_texto)


def test_indexar_sem_token_retorna_401(client, documento_texto):
    resposta = client.post("/indexar", json=documento_texto)

    assert resposta.status_code == 401


def test_indexar_token_errado_retorna_401(client, documento_texto):
    resposta = client.post(
        "/indexar",
        json=documento_texto,
        headers={"Authorization": "Bearer token-invalido"},
    )

    assert resposta.status_code == 401


def test_indexar_com_token_envia_ao_solr(client, documento_texto, mocker):
    enviar = mocker.patch("app.rotas_indexar.enviar_ao_solr")

    resposta = client.post(
        "/indexar",
        json=documento_texto,
        headers={"Authorization": "Bearer tok-teste"},
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"indexadas": 2}
    enviar.assert_called_once()
    args, _ = enviar.call_args
    assert args[0] == "http://solr:8983/solr/diarios"
    assert len(args[1]) == 2


def test_indexar_versao_invalida_retorna_422(client, documento_texto, mocker):
    mocker.patch("app.rotas_indexar.enviar_ao_solr")
    documento_texto["versao"] = 99

    resposta = client.post(
        "/indexar",
        json=documento_texto,
        headers={"Authorization": "Bearer tok-teste"},
    )

    assert resposta.status_code == 422
