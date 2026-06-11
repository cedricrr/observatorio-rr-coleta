"""Testes do endpoint POST /buscar (freemium: parcial sem sessão, completo com)."""

import pytest

from app.sessao import emitir_token


@pytest.fixture
def resposta_solr() -> dict:
    """Resposta congelada do Solr com grouping por chave_pdf + highlighting."""
    return {
        "grouped": {
            "chave_pdf": {
                "matches": 7,
                "ngroups": 5,
                "groups": [
                    {
                        "groupValue": "mprr/2022/04/2022-04-26-4.pdf",
                        "doclist": {
                            "numFound": 2,
                            "docs": [
                                {
                                    "id": "mprr/2022/04/2022-04-26-4.pdf#3",
                                    "orgao": "mprr",
                                    "data_edicao": "2022-04-26T00:00:00Z",
                                    "numero": 4,
                                    "pagina": 3,
                                    "chave_pdf": "mprr/2022/04/2022-04-26-4.pdf",
                                    "texto": "Portaria nomeando João da Silva para o cargo",
                                }
                            ],
                        },
                    },
                    {
                        "groupValue": "tjrr/2021/06/2021-06-15.pdf",
                        "doclist": {
                            "numFound": 1,
                            "docs": [
                                {
                                    "id": "tjrr/2021/06/2021-06-15.pdf#12",
                                    "orgao": "tjrr",
                                    "data_edicao": "2021-06-15T00:00:00Z",
                                    "pagina": 12,
                                    "chave_pdf": "tjrr/2021/06/2021-06-15.pdf",
                                    "texto": "Intimação de João da Silva no processo",
                                }
                            ],
                        },
                    },
                ],
            }
        },
        "highlighting": {
            "mprr/2022/04/2022-04-26-4.pdf#3": {
                "texto": ["Portaria nomeando <em>João</em> da <em>Silva</em> para o cargo"]
            },
            "tjrr/2021/06/2021-06-15.pdf#12": {
                "texto": ["Intimação de <em>João</em> da <em>Silva</em> no processo"]
            },
        },
    }


def test_buscar_sem_sessao_retorna_parcial(client, resposta_solr, mocker):
    consultar = mocker.patch(
        "app.rotas_buscar.consultar_solr", return_value=resposta_solr,
    )

    resposta = client.post("/buscar", json={"q": "João da Silva"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["parcial"] is True
    assert corpo["total_diarios"] == 5
    assert corpo["total_ocorrencias"] == 7
    assert len(corpo["resultados"]) == 2
    _, params = consultar.call_args[0]
    assert params["rows"] == 3
    assert params["group"] == "true"
    assert params["group.field"] == "chave_pdf"
    assert params["hl"] == "true"


def test_buscar_resultado_montado_com_url_e_trecho(client, resposta_solr, mocker):
    mocker.patch("app.rotas_buscar.consultar_solr", return_value=resposta_solr)

    corpo = client.post("/buscar", json={"q": "João da Silva"}).json()

    r = corpo["resultados"][0]
    assert r["orgao"] == "mprr"
    assert r["data_edicao"] == "2022-04-26"
    assert r["numero"] == 4
    assert r["pagina"] == 3
    assert r["trecho_html"] == "Portaria nomeando <em>João</em> da <em>Silva</em> para o cargo"
    assert r["url_pdf"] == (
        "https://observatoriorr.com.br/mprr/2022/04/2022-04-26-4.pdf#page=3"
    )
    assert corpo["resultados"][1]["numero"] is None


def test_buscar_com_sessao_valida_retorna_completo(client, config, resposta_solr, mocker):
    consultar = mocker.patch(
        "app.rotas_buscar.consultar_solr", return_value=resposta_solr,
    )
    token = emitir_token(config.session_secret)

    corpo = client.post(
        "/buscar",
        json={"q": "João da Silva", "offset": 20},
        headers={"X-Sessao": token},
    ).json()

    assert corpo["parcial"] is False
    _, params = consultar.call_args[0]
    assert params["rows"] == 20
    assert params["start"] == 20


def test_buscar_sessao_invalida_retorna_401(client, resposta_solr, mocker):
    mocker.patch("app.rotas_buscar.consultar_solr", return_value=resposta_solr)

    resposta = client.post(
        "/buscar",
        json={"q": "João"},
        headers={"X-Sessao": "token-adulterado"},
    )

    assert resposta.status_code == 401


def test_buscar_sem_highlight_usa_inicio_do_texto_escapado(client, resposta_solr, mocker):
    resposta_solr["highlighting"] = {}
    resposta_solr["grouped"]["chave_pdf"]["groups"][0]["doclist"]["docs"][0]["texto"] = (
        "Texto com <tag> & caracteres especiais"
    )
    mocker.patch("app.rotas_buscar.consultar_solr", return_value=resposta_solr)

    corpo = client.post("/buscar", json={"q": "João"}).json()

    assert "<tag>" not in corpo["resultados"][0]["trecho_html"]
    assert "&lt;tag&gt;" in corpo["resultados"][0]["trecho_html"]


def test_buscar_q_vazio_retorna_422(client):
    resposta = client.post("/buscar", json={"q": "  "})

    assert resposta.status_code == 422


def test_buscar_offset_negativo_retorna_422(client):
    resposta = client.post("/buscar", json={"q": "João", "offset": -1})

    assert resposta.status_code == 422
