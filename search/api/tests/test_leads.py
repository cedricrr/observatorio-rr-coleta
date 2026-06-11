"""Testes do endpoint POST /leads (captura com consentimento LGPD)."""

from app.db import gravar_lead
from app.sessao import verificar_token


def test_lead_sem_consentimento_retorna_400(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads",
        json={"email": "fulano@example.com", "consentimento": False},
    )

    assert resposta.status_code == 400
    gravar.assert_not_called()


def test_lead_email_invalido_retorna_422(client, mocker):
    mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads",
        json={"email": "nao-e-email", "consentimento": True},
    )

    assert resposta.status_code == 422


def test_lead_valido_grava_e_devolve_token(client, config, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads",
        json={
            "email": "fulano@example.com",
            "telefone": "+55 95 99999-0000",
            "consentimento": True,
            "origem_busca": "João da Silva",
        },
    )

    assert resposta.status_code == 200
    token = resposta.json()["token"]
    assert verificar_token(token, config.session_secret) is True
    _, kwargs = gravar.call_args
    assert kwargs["email"] == "fulano@example.com"
    assert kwargs["telefone"] == "+55 95 99999-0000"
    assert kwargs["origem_busca"] == "João da Silva"
    assert "Observatório" in kwargs["finalidade"]


def test_lead_telefone_opcional(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads",
        json={"email": "fulano@example.com", "consentimento": True},
    )

    assert resposta.status_code == 200
    assert gravar.call_args[1]["telefone"] is None


def test_gravar_lead_faz_upsert_por_email(mocker):
    conexao = mocker.MagicMock()
    connect = mocker.patch("app.db.psycopg.connect")
    connect.return_value.__enter__.return_value = conexao

    gravar_lead(
        "postgresql://x",
        email="Fulano@Example.com",
        telefone=None,
        finalidade="comunicações do Observatório Roraima",
        origem_busca=None,
    )

    sqls = [chamada.args[0] for chamada in conexao.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS leads" in s for s in sqls)
    insert = next(s for s in sqls if "INSERT INTO leads" in s)
    assert "ON CONFLICT" in insert
