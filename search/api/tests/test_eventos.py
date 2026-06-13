"""Testes do endpoint POST /eventos (funil — Sessão 13, Ciclo 13.2).

Mede as 4 etapas do funil sem analytics pago. O evento é anterior ao
consentimento: o payload aceita SOMENTE {tipo, sessao} — sem IP, sem
user agent, sem qualquer dado pessoal. `sessao` é um id anônimo gerado
no cliente.
"""

import re

import pytest

from app.db import gravar_evento

TIPOS_VALIDOS = ["home_view", "busca_exec", "gate_view", "cadastro_ok"]


def corpo_valido(**extras) -> dict:
    corpo = {"tipo": "busca_exec", "sessao": "a1b2c3d4e5f6a7b8"}
    corpo.update(extras)
    return corpo


# ---------------------------------------------------------------------------
# Gravação por tipo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", TIPOS_VALIDOS)
def test_evento_valido_grava_e_retorna_201(client, mocker, tipo):
    gravar = mocker.patch("app.rotas_eventos.gravar_evento")

    resposta = client.post("/eventos", json=corpo_valido(tipo=tipo))

    assert resposta.status_code == 201
    kwargs = gravar.call_args.kwargs
    assert kwargs["tipo"] == tipo
    assert kwargs["sessao_id"] == "a1b2c3d4e5f6a7b8"


def test_resposta_nao_ecoa_nada(client, mocker):
    mocker.patch("app.rotas_eventos.gravar_evento")

    resposta = client.post("/eventos", json=corpo_valido())

    assert resposta.json() == {}


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


def test_tipo_desconhecido_retorna_422(client, mocker):
    gravar = mocker.patch("app.rotas_eventos.gravar_evento")

    resposta = client.post("/eventos", json=corpo_valido(tipo="pageview"))

    assert resposta.status_code == 422
    gravar.assert_not_called()


def test_campo_extra_e_rejeitado(client, mocker):
    # dado pessoal não entra nem por engano: payload é fechado
    gravar = mocker.patch("app.rotas_eventos.gravar_evento")

    resposta = client.post(
        "/eventos", json=corpo_valido(email="fulano@example.com")
    )

    assert resposta.status_code == 422
    gravar.assert_not_called()


def test_sessao_ausente_retorna_422(client, mocker):
    gravar = mocker.patch("app.rotas_eventos.gravar_evento")

    resposta = client.post("/eventos", json={"tipo": "home_view"})

    assert resposta.status_code == 422
    gravar.assert_not_called()


def test_sessao_vazia_ou_longa_demais_retorna_422(client, mocker):
    gravar = mocker.patch("app.rotas_eventos.gravar_evento")

    vazia = client.post("/eventos", json=corpo_valido(sessao=""))
    longa = client.post("/eventos", json=corpo_valido(sessao="x" * 65))

    assert vazia.status_code == 422
    assert longa.status_code == 422
    gravar.assert_not_called()


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_eventos_rate_limit_60_por_minuto(client, mocker):
    mocker.patch("app.rotas_eventos.gravar_evento")

    codigos = [
        client.post("/eventos", json=corpo_valido()).status_code
        for _ in range(61)
    ]

    assert codigos[:60] == [201] * 60
    assert codigos[60] == 429


# ---------------------------------------------------------------------------
# Persistência (app/db.py)
# ---------------------------------------------------------------------------


def test_gravar_evento_cria_tabela_e_insere(mocker):
    conexao = mocker.MagicMock()
    connect = mocker.patch("app.db.psycopg.connect")
    connect.return_value.__enter__.return_value = conexao

    gravar_evento("postgresql://x", tipo="gate_view", sessao_id="a1b2c3d4")

    sqls = [chamada.args[0] for chamada in conexao.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS eventos" in s for s in sqls)
    assert any("INSERT INTO eventos" in s for s in sqls)


def test_tabela_eventos_nao_tem_colunas_de_dado_pessoal(mocker):
    # contrato: evento é pré-consentimento — sem IP, user agent, e-mail etc.
    conexao = mocker.MagicMock()
    connect = mocker.patch("app.db.psycopg.connect")
    connect.return_value.__enter__.return_value = conexao

    gravar_evento("postgresql://x", tipo="home_view", sessao_id="a1b2c3d4")

    sqls = " ".join(chamada.args[0] for chamada in conexao.execute.call_args_list)
    for proibido in ("ip", "ip_hash", "user_agent", "email", "telefone", "nome"):
        assert re.search(rf"\b{proibido}\b", sqls) is None
