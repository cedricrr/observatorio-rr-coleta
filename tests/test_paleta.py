"""Guarda da paleta institucional (Sessão 13.5, seção 6.2 do diagnóstico).

A paleta vive como variáveis CSS no :root de cada template. Decisão de
design registrada: o vermelho #c8102e e o azul #1d4e89 deixam de ser
cromo da interface e ficam SÓ como identidade dos órgãos (MPRR/TJRR).
"""

from pathlib import Path

import pytest

TEMPLATES_DIR = Path("scripts/templates")
TEMPLATES = [
    "indice.html.j2",
    "jornal.html.j2",
    "busca.html.j2",
    "cadastro.html.j2",
    "privacidade.html.j2",
    "sobre.html.j2",
    "diarios.html.j2",
]


@pytest.mark.parametrize("nome", TEMPLATES)
def test_template_usa_paleta_institucional(nome):
    css = (TEMPLATES_DIR / nome).read_text(encoding="utf-8")
    assert "--cor-primaria: #0F2A3D" in css
    assert "--cor-primaria-apoio: #1D4E6B" in css
    assert "--cor-cta: #1E6B4F" in css
    assert "--cor-fundo: #FAF8F4" in css
    assert "--cor-superficie: #FFFFFF" in css
    assert "--cor-texto: #1A1A1A" in css
    assert "--cor-texto-sec: #5C6670" in css
    assert "--cor-dado: #B07D2B" in css
    assert "--cor-em-breve: #8A99A8" in css


@pytest.mark.parametrize("nome", TEMPLATES)
def test_cromo_antigo_removido(nome):
    css = (TEMPLATES_DIR / nome).read_text(encoding="utf-8")
    assert "--cor-primaria: #1a1a1a" not in css
    assert "--cor-texto: #2c2c2c" not in css
    assert "--cor-rule: #c8102e" not in css  # vermelho não é mais cromo


def test_identidade_dos_orgaos_preservada():
    css = (TEMPLATES_DIR / "busca.html.j2").read_text(encoding="utf-8")
    assert "--cor-mprr: #c8102e" in css
    assert "--cor-tjrr: #1d4e89" in css
    assert "var(--cor-mprr)" in css  # badge MPRR usa a cor de identidade
    assert "var(--cor-tjrr)" in css


@pytest.mark.parametrize("nome", ["busca.html.j2", "cadastro.html.j2"])
def test_blur_do_gate_sem_overlay_escuro(nome):
    css = (TEMPLATES_DIR / nome).read_text(encoding="utf-8")
    assert "blur(6px) saturate(0.7)" in css
    assert "rgba(0, 0, 0, 0.5)" not in css  # sem véu escuro sobre o gate
