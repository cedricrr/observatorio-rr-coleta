"""Testes do módulo fontes.tjrr (fase RED — implementação ainda não existe)."""

from datetime import date

import pytest
import requests

from fontes.tjrr import discover


def _resp(status: int):
    class _R:
        status_code = status
    return _R()


def _head_kwargs(mock_head):
    """Devolve os kwargs da única chamada de requests.head."""
    return mock_head.call_args.kwargs


def _head_url(mock_head):
    """Devolve a URL passada para requests.head (positional ou kwarg)."""
    call = mock_head.call_args
    if call.args:
        return call.args[0]
    return call.kwargs["url"]


def test_discover_monta_url_correta_para_data(mocker):
    head = mocker.patch("requests.head", return_value=_resp(200))

    discover(date(2026, 4, 30))

    assert _head_url(head).endswith("dpj-20260430.pdf")


def test_discover_retorna_dict_com_campos_corretos_em_200(mocker):
    mocker.patch("requests.head", return_value=_resp(200))

    result = discover(date(2026, 4, 30))

    assert result == {
        "url": "https://diario.tjrr.jus.br/dpj/dpj-20260430.pdf",
        "data_edicao": "2026-04-30",
        "numero": None,
        "titulo": None,
    }


@pytest.mark.parametrize("status", [301, 401, 403, 404])
def test_discover_retorna_none_em_status_de_ausencia(mocker, status):
    """3xx/4xx = diário não existe naquela URL — ausência real, não erro."""
    mocker.patch("requests.head", return_value=_resp(status))
    assert discover(date(2026, 4, 30)) is None


@pytest.mark.parametrize("status", [500, 502, 503])
def test_discover_levanta_em_erro_de_servidor(mocker, status):
    """5xx = servidor com problema — deve virar 'erro' re-rodável no backfill,
    nunca 'sem_diario' silencioso."""
    mocker.patch("requests.head", return_value=_resp(status))
    with pytest.raises(requests.HTTPError):
        discover(date(2026, 4, 30))


def test_discover_propaga_timeout(mocker):
    """Timeout NÃO é ausência de diário — propaga para o chamador marcar 'erro'."""
    mocker.patch("requests.head", side_effect=requests.Timeout("timed out"))

    with pytest.raises(requests.Timeout):
        discover(date(2026, 4, 30))


def test_discover_propaga_connection_error(mocker):
    mocker.patch("requests.head", side_effect=requests.ConnectionError("no route"))

    with pytest.raises(requests.ConnectionError):
        discover(date(2026, 4, 30))


def test_discover_usa_user_agent_observatorio(mocker):
    head = mocker.patch("requests.head", return_value=_resp(200))

    discover(date(2026, 4, 30))

    headers = _head_kwargs(head)["headers"]
    assert "ObservatorioRoraima" in headers["User-Agent"]


def test_discover_usa_timeout_razoavel(mocker):
    head = mocker.patch("requests.head", return_value=_resp(200))

    discover(date(2026, 4, 30))

    timeout = _head_kwargs(head)["timeout"]
    assert isinstance(timeout, (int, float))
    assert 5 <= timeout <= 30


def test_discover_data_de_um_digito_zero_pad(mocker):
    head = mocker.patch("requests.head", return_value=_resp(200))

    discover(date(2026, 1, 5))

    assert _head_url(head).endswith("dpj-20260105.pdf")
