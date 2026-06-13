"""Testes do endpoint POST /leads (contrato da Sessão 13 — Ciclo 13.1).

Contrato novo (quebra o antigo de propósito; frontend e API sobem juntos):
  body: { nome, email, telefone?, consentimentos: {relatorios, ofertas?}, termos: [..] }
  resposta 201: { token }
"""

import hashlib

from app.db import gravar_lead
from app.sessao import verificar_token


def corpo_valido(**extras) -> dict:
    corpo = {
        "nome": "Fulano de Tal",
        "email": "fulano@example.com",
        "consentimentos": {"relatorios": True, "ofertas": False},
        "termos": ["João da Silva"],
    }
    corpo.update(extras)
    return corpo


# ---------------------------------------------------------------------------
# Caminho feliz
# ---------------------------------------------------------------------------


def test_lead_valido_grava_e_devolve_token_201(client, config, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido())

    assert resposta.status_code == 201
    token = resposta.json()["token"]
    assert verificar_token(token, config.session_secret) is True
    kwargs = gravar.call_args.kwargs
    assert kwargs["nome"] == "Fulano de Tal"
    assert kwargs["email"] == "fulano@example.com"
    assert kwargs["telefone"] is None
    assert kwargs["consentimento_relatorios"] is True
    assert kwargs["consentimento_ofertas"] is False
    assert kwargs["termos_sessao"] == ["João da Silva"]
    assert "Observatório" in kwargs["finalidade"]


def test_resposta_so_contem_o_token(client, mocker):
    # nunca ecoar dados do lead (nem de outros) na resposta
    mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido())

    assert set(resposta.json().keys()) == {"token"}


# ---------------------------------------------------------------------------
# Consentimento granular
# ---------------------------------------------------------------------------


def test_sem_checkbox_relatorios_retorna_422(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    corpo = corpo_valido(consentimentos={"relatorios": False, "ofertas": True})
    resposta = client.post("/leads", json=corpo)

    assert resposta.status_code == 422
    gravar.assert_not_called()


def test_ofertas_ausente_grava_false(client, mocker):
    # opt-in nunca é assumido: checkbox 2 ausente == desmarcado
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    corpo = corpo_valido(consentimentos={"relatorios": True})
    resposta = client.post("/leads", json=corpo)

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["consentimento_ofertas"] is False


def test_payload_antigo_rejeitado_com_mensagem_clara(client, mocker):
    # contrato da Sessão 11: {email, consentimento, origem_busca} — sem nome
    # nem consentimentos. Deve falhar citando os campos que faltam.
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads",
        json={
            "email": "fulano@example.com",
            "consentimento": True,
            "origem_busca": "João da Silva",
        },
    )

    assert resposta.status_code == 422
    corpo = resposta.text
    assert "nome" in corpo
    assert "consentimentos" in corpo
    gravar.assert_not_called()


# ---------------------------------------------------------------------------
# Validação de campos
# ---------------------------------------------------------------------------


def test_email_invalido_retorna_422(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido(email="nao-e-email"))

    assert resposta.status_code == 422
    gravar.assert_not_called()


def test_nome_vazio_retorna_422(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido(nome="   "))

    assert resposta.status_code == 422
    gravar.assert_not_called()


# ---------------------------------------------------------------------------
# Telefone → E.164 BR
# ---------------------------------------------------------------------------


def test_telefone_celular_normalizado_para_e164(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads", json=corpo_valido(telefone="(95) 99123-4567")
    )

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["telefone"] == "+5595991234567"


def test_telefone_fixo_normalizado_para_e164(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido(telefone="95 3621-0000"))

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["telefone"] == "+559536210000"


def test_telefone_ja_em_e164_passa_inalterado(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads", json=corpo_valido(telefone="+5595991234567")
    )

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["telefone"] == "+5595991234567"


def test_telefone_com_55_sem_mais_normaliza(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads", json=corpo_valido(telefone="55 95 99123-4567")
    )

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["telefone"] == "+5595991234567"


def test_telefone_invalido_retorna_422(client, mocker):
    # sem DDD não há como montar E.164 — rejeitar em vez de gravar lixo
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido(telefone="1234"))

    assert resposta.status_code == 422
    gravar.assert_not_called()


def test_telefone_ausente_continua_opcional(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido())

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["telefone"] is None


# ---------------------------------------------------------------------------
# Termos da sessão e classe
# ---------------------------------------------------------------------------


def test_termos_tecnicos_classificam_como_tecnico(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    corpo = corpo_valido(termos=["intimação", "João da Silva"])
    resposta = client.post("/leads", json=corpo)

    assert resposta.status_code == 201
    kwargs = gravar.call_args.kwargs
    assert kwargs["termos_sessao"] == ["intimação", "João da Silva"]
    assert kwargs["classe"] == "tecnico"


def test_termos_gerais_classificam_como_geral(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido(termos=["João da Silva"]))

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["classe"] == "geral"


def test_termos_vazio_e_aceito_e_classifica_geral(client, mocker):
    # cadastro vindo de fluxo sem busca registrada não pode quebrar
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido(termos=[]))

    assert resposta.status_code == 201
    assert gravar.call_args.kwargs["classe"] == "geral"


# ---------------------------------------------------------------------------
# ip_hash (auditoria de consentimento)
# ---------------------------------------------------------------------------


def test_ip_hash_usa_primeiro_hop_do_x_forwarded_for(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post(
        "/leads",
        json=corpo_valido(),
        headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"},
    )

    assert resposta.status_code == 201
    esperado = hashlib.sha256(b"203.0.113.7").hexdigest()[:16]
    assert gravar.call_args.kwargs["ip_hash"] == esperado


def test_ip_hash_sem_header_usa_ip_da_conexao(client, mocker):
    gravar = mocker.patch("app.rotas_leads.gravar_lead")

    resposta = client.post("/leads", json=corpo_valido())

    assert resposta.status_code == 201
    # TestClient conecta como "testclient"
    esperado = hashlib.sha256(b"testclient").hexdigest()[:16]
    assert gravar.call_args.kwargs["ip_hash"] == esperado


# ---------------------------------------------------------------------------
# Persistência (app/db.py)
# ---------------------------------------------------------------------------


def kwargs_gravar(**extras) -> dict:
    kwargs = {
        "nome": "Fulano de Tal",
        "email": "Fulano@Example.com",
        "telefone": None,
        "consentimento_relatorios": True,
        "consentimento_ofertas": False,
        "classe": "geral",
        "termos_sessao": ["João da Silva"],
        "ip_hash": "abc123",
        "finalidade": "comunicações do Observatório Roraima",
    }
    kwargs.update(extras)
    return kwargs


def test_gravar_lead_faz_upsert_por_email(mocker):
    conexao = mocker.MagicMock()
    connect = mocker.patch("app.db.psycopg.connect")
    connect.return_value.__enter__.return_value = conexao

    gravar_lead("postgresql://x", **kwargs_gravar())

    sqls = [chamada.args[0] for chamada in conexao.execute.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS leads" in s for s in sqls)
    insert = next(s for s in sqls if "INSERT INTO leads" in s)
    assert "ON CONFLICT" in insert


def test_ddl_evolui_schema_com_colunas_novas(mocker):
    # convenção do projeto: sem ferramenta de migração — ALTER TABLE
    # ADD COLUMN IF NOT EXISTS na mesma conexão do insert
    conexao = mocker.MagicMock()
    connect = mocker.patch("app.db.psycopg.connect")
    connect.return_value.__enter__.return_value = conexao

    gravar_lead("postgresql://x", **kwargs_gravar())

    sqls = " ".join(
        chamada.args[0] for chamada in conexao.execute.call_args_list
    )
    for coluna in (
        "nome",
        "consentimento_relatorios",
        "consentimento_ofertas",
        "classe",
        "termos_sessao",
        "ip_hash",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {coluna}" in sqls


def test_upsert_renova_campos_novos_no_conflito(mocker):
    # e-mail duplicado renova consentimento e atualiza os campos novos,
    # sem criar registro (idempotência herdada da Sessão 11)
    conexao = mocker.MagicMock()
    connect = mocker.patch("app.db.psycopg.connect")
    connect.return_value.__enter__.return_value = conexao

    gravar_lead("postgresql://x", **kwargs_gravar())

    insert = next(
        chamada.args[0]
        for chamada in conexao.execute.call_args_list
        if "INSERT INTO leads" in chamada.args[0]
    )
    trecho_update = insert.split("ON CONFLICT")[1]
    for coluna in (
        "nome",
        "consentimento_relatorios",
        "consentimento_ofertas",
        "classe",
        "termos_sessao",
        "consentimento_em",
    ):
        assert coluna in trecho_update
