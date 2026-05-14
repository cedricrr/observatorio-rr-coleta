"""Testes do scripts.baixar_pdf (fase RED — implementação ainda não existe)."""

import pytest
from unittest.mock import MagicMock

from scripts.baixar_pdf import baixar_pdf_do_r2


def test_chave_valida_retorna_bytes():
    r2_mock = MagicMock()
    r2_mock.download_bytes.return_value = b"%PDF-1.4\n..."

    resultado = baixar_pdf_do_r2("mprr/2024/01/2024-01-02-399.pdf", r2_mock)

    assert isinstance(resultado, bytes)
    assert resultado.startswith(b"%PDF")
    assert r2_mock.download_bytes.called
    r2_mock.download_bytes.assert_called_once_with(
        "mprr/2024/01/2024-01-02-399.pdf"
    )


def test_chave_vazia_levanta_valueerror():
    r2_mock = MagicMock()

    with pytest.raises(ValueError, match="chave"):
        baixar_pdf_do_r2("", r2_mock)

    assert not r2_mock.download_bytes.called


def test_chave_apenas_espacos_levanta_valueerror():
    r2_mock = MagicMock()

    with pytest.raises(ValueError):
        baixar_pdf_do_r2("   ", r2_mock)

    assert not r2_mock.download_bytes.called


def test_r2_levanta_excecao_propaga():
    r2_mock = MagicMock()
    r2_mock.download_bytes.side_effect = RuntimeError("chave não existe")

    with pytest.raises(RuntimeError, match="chave não existe"):
        baixar_pdf_do_r2("inexistente.pdf", r2_mock)


def test_bytes_vazios_levanta_valueerror():
    r2_mock = MagicMock()
    r2_mock.download_bytes.return_value = b""

    with pytest.raises(ValueError, match="vazi"):
        baixar_pdf_do_r2("chave.pdf", r2_mock)


def test_bytes_nao_sao_pdf_levanta_valueerror():
    r2_mock = MagicMock()
    r2_mock.download_bytes.return_value = b"isso nao eh PDF"

    with pytest.raises(ValueError, match="PDF"):
        baixar_pdf_do_r2("chave.pdf", r2_mock)


def test_chave_com_path_completo_funciona():
    r2_mock = MagicMock()
    r2_mock.download_bytes.return_value = b"%PDF-1.7\n..."

    resultado = baixar_pdf_do_r2("tjrr/2024/06/2024-06-15-123.pdf", r2_mock)

    assert resultado.startswith(b"%PDF")
    r2_mock.download_bytes.assert_called_once_with(
        "tjrr/2024/06/2024-06-15-123.pdf"
    )
