"""Testes do token de sessão freemium (app.sessao)."""

import time

from app.sessao import VALIDADE_SEGUNDOS, emitir_token, verificar_token


def test_round_trip_token_valido():
    token = emitir_token("s3gredo")

    assert verificar_token(token, "s3gredo") is True


def test_token_adulterado_e_invalido():
    token = emitir_token("s3gredo")

    assert verificar_token(token + "x", "s3gredo") is False


def test_token_com_segredo_errado_e_invalido():
    token = emitir_token("s3gredo")

    assert verificar_token(token, "outro-segredo") is False


def test_token_lixo_e_invalido():
    assert verificar_token("nao-e-um-token", "s3gredo") is False
    assert verificar_token("", "s3gredo") is False


def test_token_expirado_e_invalido(mocker):
    agora = time.time()
    mocker.patch("time.time", return_value=agora - VALIDADE_SEGUNDOS - 60)
    token = emitir_token("s3gredo")
    mocker.patch("time.time", return_value=agora)

    assert verificar_token(token, "s3gredo") is False


def test_validade_e_cerca_de_180_dias():
    assert VALIDADE_SEGUNDOS == 180 * 24 * 60 * 60
