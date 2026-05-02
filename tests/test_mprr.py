"""Testes do módulo fontes.mprr (fase RED — implementação ainda não existe)."""

from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from fontes.mprr import (
    _extract_month_jsons,
    _fetch_year_html,
    _get_session_with_csrf,
    _parse_item,
    discover,
    list_year,
    list_years,
)


HTML_FIXTURE = '''<!DOCTYPE html>
<html>
<head>
  <meta name="csrf-token" content="csrf-token-fake-1234">
</head>
<body>
<script>
var dados1 = [
  {"start":"2026-01-05","end":"2026-01-05","title":"Diário Eletrônico do MPRR n. 879-2026","url":"\\/servicos\\/download\\/diario-eletronico-do-mprr-n-879-2026-2025-12-30-12-51-17.pdf","allDay":"true"},
  {"start":"2026-01-06","end":"2026-01-06","title":"Diário Eletrônico do MPRR n. 880-2025","url":"\\/servicos\\/download\\/diario-eletronico-do-mprr-n-880-2025-2026-01-05-14-13-36.pdf","allDay":"true"}
];
var dados2 = [];
var dados3 = [
  {"start":"2026-03-26","end":"2026-03-26","title":"Diário Eletrônico do MPRR n. 931-2026","url":"\\/servicos\\/download\\/diario-eletronico-do-mprr-n-931-2026-2026-03-25-16-59-44.pdf","allDay":"true"}
];
var dados4 = [
  {"start":"2026-04-30","end":"2026-04-30","title":"Diário Eletrônico do MPRR n. 951-2026","url":"\\/servicos\\/download\\/diario-eletronico-do-mprr-n-951-2026-2026-04-29-17-58-10.pdf","allDay":"true"}
];
var dados5 = [];
var dados6 = [];
var dados7 = [];
var dados8 = [];
var dados9 = [];
var dados10 = [];
var dados11 = [];
var dados12 = [];
</script>
</body>
</html>
'''


# --------------------------------------------------------------------------
# GRUPO A: _extract_month_jsons
# --------------------------------------------------------------------------

def test_extract_month_jsons_pega_todos_os_meses_com_dados():
    items = _extract_month_jsons(HTML_FIXTURE)

    assert len(items) == 4
    starts = [it["start"] for it in items]
    assert starts == sorted(starts)
    assert starts == ["2026-01-05", "2026-01-06", "2026-03-26", "2026-04-30"]


def test_extract_month_jsons_resolve_escape_de_barras_json():
    """Garante que \\/ no HTML vira / após json.loads."""
    items = _extract_month_jsons(HTML_FIXTURE)

    # No HTML_FIXTURE, a edição 951 tem url com \\/servicos\\/...
    edicao_951 = next(it for it in items if it["start"] == "2026-04-30")
    assert "\\\\/" not in edicao_951["url"]
    assert edicao_951["url"].startswith("/servicos/download/")


def test_extract_month_jsons_retorna_lista_vazia_se_nada():
    html_vazio = "<html><body><p>nada aqui</p></body></html>"

    assert _extract_month_jsons(html_vazio) == []


def test_extract_month_jsons_tolera_dadosN_invalido():
    html = """
<script>
var dados1 = [nao-eh-json-valido];
var dados2 = [{"start":"2026-02-01","end":"2026-02-01","title":"Diário Eletrônico do MPRR n. 900-2026","url":"/x.pdf","allDay":"true"}];
</script>
"""
    items = _extract_month_jsons(html)

    assert len(items) == 1
    assert items[0]["start"] == "2026-02-01"


# --------------------------------------------------------------------------
# GRUPO B: _parse_item
# --------------------------------------------------------------------------

def test_parse_item_resolve_data_do_start_ignorando_ano_do_titulo():
    raw = {
        "start": "2026-01-06",
        "end": "2026-01-06",
        "title": "Diário Eletrônico do MPRR n. 880-2025",
        "url": "/servicos/download/x.pdf",
    }

    parsed = _parse_item(raw)

    assert parsed is not None
    assert parsed["data_edicao"] == "2026-01-06"
    assert parsed["numero"] == 880


def test_parse_item_extrai_numero_de_titulo_normal():
    raw = {
        "start": "2026-04-30",
        "title": "Diário Eletrônico do MPRR n. 951-2026",
        "url": "/x.pdf",
    }

    parsed = _parse_item(raw)

    assert parsed is not None
    assert parsed["numero"] == 951


def test_parse_item_url_relativa_vira_absoluta():
    raw = {
        "start": "2026-04-30",
        "title": "Diário Eletrônico do MPRR n. 951-2026",
        "url": "/servicos/download/x.pdf",
    }

    parsed = _parse_item(raw)

    assert parsed is not None
    assert parsed["url"] == "https://www.mprr.mp.br/servicos/download/x.pdf"


def test_parse_item_retorna_none_se_falta_url():
    raw = {
        "start": "2026-01-06",
        "title": "Diário Eletrônico do MPRR n. 880-2026",
    }

    assert _parse_item(raw) is None


def test_parse_item_retorna_none_se_falta_start():
    raw = {
        "title": "Diário Eletrônico do MPRR n. 880-2026",
        "url": "/x.pdf",
    }

    assert _parse_item(raw) is None


def test_parse_item_inclui_titulo_original():
    raw = {
        "start": "2026-04-30",
        "title": "Diário Eletrônico do MPRR n. 951-2026",
        "url": "/x.pdf",
    }

    parsed = _parse_item(raw)

    assert parsed is not None
    assert parsed["titulo"] == "Diário Eletrônico do MPRR n. 951-2026"


# --------------------------------------------------------------------------
# GRUPO C: _get_session_with_csrf
# --------------------------------------------------------------------------

def test_get_session_with_csrf_extrai_token_do_meta_tag(mocker):
    session_mock = MagicMock()
    session_mock.headers = {}
    session_mock.get.return_value = MagicMock(text=HTML_FIXTURE)
    mocker.patch("requests.Session", return_value=session_mock)

    session, token = _get_session_with_csrf()

    assert session is session_mock
    assert token == "csrf-token-fake-1234"


def test_get_session_with_csrf_levanta_se_nao_acha_token(mocker):
    html_sem_token = "<html><head></head><body></body></html>"
    session_mock = MagicMock()
    session_mock.headers = {}
    session_mock.get.return_value = MagicMock(text=html_sem_token)
    mocker.patch("requests.Session", return_value=session_mock)

    with pytest.raises(RuntimeError):
        _get_session_with_csrf()


def test_get_session_with_csrf_define_user_agent_observatorio(mocker):
    session_mock = MagicMock()
    session_mock.headers = {}
    session_mock.get.return_value = MagicMock(text=HTML_FIXTURE)
    mocker.patch("requests.Session", return_value=session_mock)

    _get_session_with_csrf()

    assert "ObservatorioRoraima" in session_mock.headers.get("User-Agent", "")


# --------------------------------------------------------------------------
# GRUPO D: _fetch_year_html
# --------------------------------------------------------------------------

def test_fetch_year_html_faz_post_com_token_e_ano(mocker):
    session_mock = MagicMock()
    session_mock.post.return_value = MagicMock(text="<html/>")
    mocker.patch(
        "fontes.mprr._get_session_with_csrf",
        return_value=(session_mock, "tok-x"),
    )

    _fetch_year_html(2025)

    session_mock.post.assert_called_once()
    call = session_mock.post.call_args
    url = call.args[0] if call.args else call.kwargs["url"]
    assert "/servicos/diario" in url
    assert call.kwargs["data"] == {"_token": "tok-x", "ano": "2025"}


# --------------------------------------------------------------------------
# GRUPO E: list_year (integração)
# --------------------------------------------------------------------------

def test_list_year_combina_fetch_e_extract(mocker):
    mocker.patch("fontes.mprr._fetch_year_html", return_value=HTML_FIXTURE)

    items = list_year(2026)

    assert len(items) == 4
    for it in items:
        assert set(it.keys()) >= {"url", "numero", "data_edicao", "titulo"}


# --------------------------------------------------------------------------
# GRUPO F: discover
# --------------------------------------------------------------------------

def test_discover_encontra_data_existente(mocker):
    edicao_951 = {
        "url": "https://www.mprr.mp.br/servicos/download/x.pdf",
        "numero": 951,
        "data_edicao": "2026-04-30",
        "titulo": "Diário Eletrônico do MPRR n. 951-2026",
    }
    mocker.patch("fontes.mprr.list_year", return_value=[edicao_951])

    result = discover(date(2026, 4, 30))

    assert result == edicao_951


def test_discover_retorna_none_se_data_nao_existe(mocker):
    edicao_951 = {
        "url": "u",
        "numero": 951,
        "data_edicao": "2026-04-30",
        "titulo": "t",
    }
    mocker.patch("fontes.mprr.list_year", return_value=[edicao_951])

    assert discover(date(2026, 4, 29)) is None


def test_discover_retorna_none_em_erro_de_rede(mocker):
    mocker.patch(
        "fontes.mprr.list_year",
        side_effect=requests.RequestException("network down"),
    )

    assert discover(date(2026, 4, 30)) is None


# --------------------------------------------------------------------------
# GRUPO G: list_years (multi-ano)
# --------------------------------------------------------------------------

def test_list_years_concatena_resultados_de_varios_anos(mocker):
    item_2024 = {"url": "u1", "numero": 1, "data_edicao": "2024-12-15", "titulo": "t1"}
    item_2025 = {"url": "u2", "numero": 2, "data_edicao": "2025-06-20", "titulo": "t2"}

    def fake(year):
        return {2024: [item_2024], 2025: [item_2025]}[year]

    mocker.patch("fontes.mprr.list_year", side_effect=fake)

    result = list_years([2024, 2025])

    assert len(result) == 2
    assert result == [item_2024, item_2025]


def test_list_years_tolera_falha_em_um_ano(mocker):
    item_2025 = {"url": "u", "numero": 1, "data_edicao": "2025-06-20", "titulo": "t"}

    def fake(year):
        if year == 2024:
            raise requests.RequestException("erro 2024")
        return [item_2025]

    mocker.patch("fontes.mprr.list_year", side_effect=fake)

    result = list_years([2024, 2025])

    assert result == [item_2025]
