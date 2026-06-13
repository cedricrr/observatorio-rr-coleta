"""Testes do GET /health e do rate limiting."""


def test_health_ok(client, mocker):
    mocker.patch("app.rotas_health.ping_solr", return_value=True)
    mocker.patch("app.rotas_health.ping_db", return_value=True)

    resposta = client.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"solr": True, "db": True}


def test_health_solr_fora_retorna_503(client, mocker):
    mocker.patch("app.rotas_health.ping_solr", return_value=False)
    mocker.patch("app.rotas_health.ping_db", return_value=True)

    resposta = client.get("/health")

    assert resposta.status_code == 503


def test_leads_rate_limit_5_por_minuto(client, mocker):
    mocker.patch("app.rotas_leads.gravar_lead")
    corpo = {
        "email": "fulano@example.com",
        "nome": "Fulano de Tal",
        "consentimentos": {"relatorios": True},
        "termos": [],
    }

    codigos = [client.post("/leads", json=corpo).status_code for _ in range(6)]

    assert codigos[:5] == [201] * 5
    assert codigos[5] == 429
