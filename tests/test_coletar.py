"""Testes do scripts.coletar — funções core (fase RED — implementação ainda não existe)."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from scripts.config import Fonte
from scripts.coletar import (
    baixar_pdf,
    gravar_metadados,
    montar_chave_r2,
    submeter_wayback,
)


def _fake_response(status: int = 200, chunks=(b"data",), raises_http: bool = False) -> MagicMock:
    """MagicMock que simula response do requests com suporte a streaming e context manager."""
    response = MagicMock()
    response.status_code = status
    response.iter_content = MagicMock(side_effect=lambda chunk_size=None: iter(chunks))
    if raises_http:
        response.raise_for_status.side_effect = requests.HTTPError("erro http")
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


# --------------------------------------------------------------------------
# GRUPO A — baixar_pdf
# --------------------------------------------------------------------------

def test_baixar_pdf_grava_arquivo_e_retorna_hash_e_tamanho(mocker, tmp_path):
    conteudo = b"%PDF-1.4 conteudo de teste"
    mocker.patch("requests.get", return_value=_fake_response(chunks=(conteudo,)))
    destino = tmp_path / "saida.pdf"

    sha256_hex, tamanho = baixar_pdf("https://exemplo/x.pdf", destino)

    assert sha256_hex == hashlib.sha256(conteudo).hexdigest()
    assert tamanho == len(conteudo)
    assert destino.exists()
    assert destino.read_bytes() == conteudo


def test_baixar_pdf_usa_stream_true_e_timeout(mocker, tmp_path):
    get = mocker.patch("requests.get", return_value=_fake_response())

    baixar_pdf("https://exemplo/x.pdf", tmp_path / "x.pdf")

    kwargs = get.call_args.kwargs
    assert kwargs.get("stream") is True
    assert isinstance(kwargs.get("timeout"), (int, float))
    assert kwargs["timeout"] > 0


def test_baixar_pdf_levanta_em_status_4xx_ou_5xx(mocker, tmp_path):
    mocker.patch(
        "requests.get",
        return_value=_fake_response(status=500, raises_http=True),
    )

    with pytest.raises(requests.HTTPError):
        baixar_pdf("https://exemplo/x.pdf", tmp_path / "x.pdf")


def test_baixar_pdf_calcula_hash_incremental_para_arquivos_grandes(mocker, tmp_path):
    chunks = (b"AAA", b"BBB", b"CCC")
    mocker.patch("requests.get", return_value=_fake_response(chunks=chunks))
    destino = tmp_path / "grande.pdf"

    sha256_hex, tamanho = baixar_pdf("https://exemplo/x.pdf", destino)

    assert sha256_hex == hashlib.sha256(b"AAABBBCCC").hexdigest()
    assert tamanho == len(b"AAABBBCCC")
    assert destino.read_bytes() == b"AAABBBCCC"


def test_baixar_pdf_usa_streaming_real(mocker, tmp_path):
    """Garante que iter_content é chamado (não response.content).

    Protege contra implementação que carrega arquivo inteiro em memória.
    """
    response = _fake_response(chunks=(b"data",))
    mocker.patch("requests.get", return_value=response)

    baixar_pdf("https://exemplo/x.pdf", tmp_path / "x.pdf")

    response.iter_content.assert_called()


# --------------------------------------------------------------------------
# GRUPO B — submeter_wayback
# --------------------------------------------------------------------------

def test_submeter_wayback_retorna_url_em_sucesso(mocker):
    response = MagicMock()
    response.status_code = 200
    response.headers = {
        "Content-Location": "/web/20260501123456/https://exemplo/x.pdf",
    }
    mocker.patch("requests.get", return_value=response)

    result = submeter_wayback("https://exemplo/x.pdf")

    assert result == "https://web.archive.org/web/20260501123456/https://exemplo/x.pdf"


def test_submeter_wayback_retorna_none_em_erro(mocker):
    mocker.patch(
        "requests.get",
        side_effect=requests.RequestException("conexão derrubada"),
    )

    assert submeter_wayback("https://exemplo/x.pdf") is None


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500, 502, 503])
def test_submeter_wayback_retorna_none_em_qualquer_status_nao_200(mocker, status):
    response = MagicMock()
    response.status_code = status
    response.headers = {}
    mocker.patch("requests.get", return_value=response)

    assert submeter_wayback("https://exemplo/x.pdf") is None


def test_submeter_wayback_usa_timeout(mocker):
    response = MagicMock()
    response.status_code = 200
    response.headers = {"Content-Location": "/web/20260501123456/https://exemplo/x.pdf"}
    get = mocker.patch("requests.get", return_value=response)

    submeter_wayback("https://exemplo/x.pdf")

    kwargs = get.call_args.kwargs
    assert isinstance(kwargs.get("timeout"), (int, float))
    assert kwargs["timeout"] > 0


# --------------------------------------------------------------------------
# GRUPO C — gravar_metadados
# --------------------------------------------------------------------------

def test_gravar_metadados_escreve_arquivo_no_caminho_correto(tmp_path):
    meta = {"orgao": "mprr", "data_edicao": "2026-04-30", "numero": 951}

    gravar_metadados(meta, raiz=tmp_path)

    assert (tmp_path / "mprr" / "2026-04-30-951.json").exists()


def test_gravar_metadados_sem_numero_omite_sufixo(tmp_path):
    meta = {"orgao": "tjrr", "data_edicao": "2026-04-30"}

    gravar_metadados(meta, raiz=tmp_path)

    assert (tmp_path / "tjrr" / "2026-04-30.json").exists()


def test_gravar_metadados_cria_diretorios_recursivamente(tmp_path):
    meta = {"orgao": "mprr", "data_edicao": "2026-04-30", "numero": 951}

    gravar_metadados(meta, raiz=tmp_path)

    assert (tmp_path / "mprr").is_dir()


def test_gravar_metadados_serializa_json_indentado_e_utf8(tmp_path):
    meta = {
        "orgao": "mprr",
        "data_edicao": "2026-04-30",
        "numero": 951,
        "titulo": "Diário Eletrônico do MPRR n. 951-2026",
    }

    caminho = gravar_metadados(meta, raiz=tmp_path)

    raw = caminho.read_text(encoding="utf-8")
    assert "\n  " in raw
    de_volta = json.loads(raw)
    assert de_volta["titulo"] == "Diário Eletrônico do MPRR n. 951-2026"
    assert "\\u" not in raw


def test_gravar_metadados_retorna_path_escrito(tmp_path):
    meta = {"orgao": "mprr", "data_edicao": "2026-04-30", "numero": 951}

    caminho = gravar_metadados(meta, raiz=tmp_path)

    assert isinstance(caminho, Path)
    assert caminho == tmp_path / "mprr" / "2026-04-30-951.json"


# --------------------------------------------------------------------------
# GRUPO D — montar_chave_r2
# --------------------------------------------------------------------------

def _fonte(codigo: str) -> Fonte:
    return Fonte(codigo=codigo, nome="qualquer", discovery_module=codigo)


def test_montar_chave_r2_com_numero():
    chave = montar_chave_r2(
        _fonte("mprr"),
        {"data_edicao": "2026-04-30", "numero": 951},
    )

    assert chave == "mprr/2026/04/2026-04-30-951.pdf"


def test_montar_chave_r2_sem_numero():
    chave = montar_chave_r2(
        _fonte("tjrr"),
        {"data_edicao": "2026-04-30", "numero": None},
    )

    assert chave == "tjrr/2026/04/2026-04-30.pdf"


def test_montar_chave_r2_zero_pad_mes():
    chave = montar_chave_r2(
        _fonte("mprr"),
        {"data_edicao": "2026-01-05", "numero": 879},
    )

    assert chave == "mprr/2026/01/2026-01-05-879.pdf"


def test_montar_chave_r2_levanta_se_data_invalida():
    with pytest.raises(ValueError):
        montar_chave_r2(_fonte("mprr"), {"data_edicao": "2026/04/30"})
