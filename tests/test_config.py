"""Testes do scripts.config (fase RED — implementação ainda não existe)."""

import dataclasses
import importlib
import re

import pytest

from scripts.config import FONTES, Fonte, get_fonte


def test_fontes_e_lista_com_pelo_menos_dois_itens():
    assert isinstance(FONTES, list)
    assert len(FONTES) >= 2


def test_fontes_contem_mprr_e_tjrr():
    codigos = {f.codigo for f in FONTES}

    assert "mprr" in codigos
    assert "tjrr" in codigos


def test_fonte_e_dataclass_frozen():
    f = FONTES[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        f.codigo = "outro"


def test_codigos_sao_unicos():
    codigos = [f.codigo for f in FONTES]

    assert len(codigos) == len(set(codigos))


def test_codigos_sao_lowercase_alfanumericos():
    for f in FONTES:
        assert re.fullmatch(r"[a-z0-9]+", f.codigo), f"codigo inválido: {f.codigo!r}"


def test_discovery_module_existe_e_expoe_discover():
    for f in FONTES:
        mod = importlib.import_module(f"fontes.{f.discovery_module}")
        assert hasattr(mod, "discover"), f"{f.discovery_module} não expõe discover"
        assert callable(mod.discover)


def test_get_fonte_retorna_fonte_por_codigo():
    mprr = get_fonte("mprr")
    tjrr = get_fonte("tjrr")

    assert isinstance(mprr, Fonte)
    assert mprr.codigo == "mprr"
    assert isinstance(tjrr, Fonte)
    assert tjrr.codigo == "tjrr"


def test_get_fonte_levanta_keyerror_para_codigo_inexistente():
    with pytest.raises(KeyError) as exc_info:
        get_fonte("inexistente")

    assert "inexistente" in str(exc_info.value)


def test_nome_e_string_nao_vazia():
    for f in FONTES:
        assert isinstance(f.nome, str)
        assert f.nome.strip() != "", f"nome vazio em {f.codigo}"
