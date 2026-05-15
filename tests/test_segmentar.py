"""Testes do segmentador de matérias sobre Markdown (Ciclo 8.4)."""

from __future__ import annotations

import pytest

from scripts.segmentar import Materia, segmentar_materias


# ---------------------------------------------------------------------------
# Fixtures de Markdown sintético — um padrão por bloco
# ---------------------------------------------------------------------------

MD_MPRR_ATO_PGJ = """
###### **MINISTÉRIO PÚBLICO DO ESTADO DE RORAIMA**

**ATO N. 042 - PGJ**

REMOVER, a pedido, por critério de merecimento, a Procuradora de
Justiça, Dra. MARIA DA SILVA, da 5ª Procuradoria de Justiça Criminal
para a 3ª Procuradoria de Justiça Criminal.
"""

MD_MPRR_EXTRATO_CONTRATO = """
**EXTRATO DO CONTRATO N. 25/2026**

CONTRATADA: EMPRESA EXEMPLO LTDA - CNPJ 00.000.000/0001-00
OBJETO: aquisição de caminhão médio com baú
VALOR: R$ 429.000,00
"""

MD_MPRR_INSTAURACAO_IC = """
**EXTRATO DA PORTARIA DE INSTAURAÇÃO DE IC N. 10/2026**

O Promotor de Justiça da Comarca de Bonfim instaurou inquérito civil
cujo objeto é "apurar suposta prática de improbidade administrativa
no município de Bonfim".
"""

MD_MPRR_DISPENSA_LICITACAO = """
**EXTRATO DE DISPENSA DE LICITAÇÃO N. 05/2026**

CONTRATADO: FORNECEDOR LTDA
OBJETO: instalação de cerca eletrificada na nova Promotoria
VALOR: R$ 35.000,00
Fundamentação: art. 75, II, Lei 14.133/2021.
"""

MD_TJRR_EMENDA_REGIMENTAL = """
###### **TRIBUNAL PLENO**

**EMENDA REGIMENTAL TJRR/TP N. 15**

Altera dispositivos do Regimento Interno do Tribunal sobre
afastamento de desembargadores e quórum em ações de
inconstitucionalidade.
"""

MD_TJRR_PORTARIA_ITEM = """
###### **PRESIDÊNCIA**

**PORTARIA TJRR/PR N. 337, DE 22 DE ABRIL DE 2026.**

N. 1 - Designar o servidor JOÃO DA SILVA, Analista Judiciário,
para exercer a função de Diretor de Secretaria.

N. 2 - Lotar o servidor PEDRO COSTA, Analista de Sistemas, na
Subsecretaria de Cibersegurança.
"""

MD_TJRR_EXTRATO_CONTRATO = """
**EXTRATO DE CONTRATO N. 5/2026**

CONTRATADA: FUTURA CLIMATIZAÇÃO LTDA
OBJETO: aquisição de centrais split e cortinas de ar
VALOR: R$ 158.000,00
"""


# ---------------------------------------------------------------------------
# GRUPO A — Dataclass Materia
# ---------------------------------------------------------------------------

def test_materia_e_dataclass_com_campos_essenciais():
    m = Materia(
        orgao="MPRR",
        tipo="ATO_PGJ",
        texto="conteudo",
        pdf_url="https://example.com/a.pdf",
    )
    assert m.orgao == "MPRR"
    assert m.tipo == "ATO_PGJ"
    assert m.texto == "conteudo"
    assert m.pdf_url == "https://example.com/a.pdf"
    assert m.pagina is None


def test_materia_aceita_pagina_opcional():
    m = Materia(
        orgao="MPRR",
        tipo="ATO_PGJ",
        texto="x",
        pdf_url="y",
        pagina=5,
    )
    assert m.pagina == 5


# ---------------------------------------------------------------------------
# GRUPO B — segmentar_materias (MPRR)
# ---------------------------------------------------------------------------

def test_segmentar_mprr_detecta_ato_pgj():
    materias = segmentar_materias(MD_MPRR_ATO_PGJ, "MPRR", "https://test.pdf")
    assert len(materias) >= 1
    assert any(m.tipo == "ATO_PGJ" for m in materias)
    m = next(m for m in materias if m.tipo == "ATO_PGJ")
    assert m.orgao == "MPRR"
    assert "REMOVER" in m.texto
    assert m.pdf_url == "https://test.pdf"


def test_segmentar_mprr_detecta_extrato_contrato():
    materias = segmentar_materias(MD_MPRR_EXTRATO_CONTRATO, "MPRR", "https://x.pdf")
    assert any(m.tipo == "EXTRATO_CONTRATO" for m in materias)
    m = next(m for m in materias if m.tipo == "EXTRATO_CONTRATO")
    assert "CONTRATADA" in m.texto
    assert "429.000" in m.texto


def test_segmentar_mprr_detecta_instauracao_ic():
    materias = segmentar_materias(MD_MPRR_INSTAURACAO_IC, "MPRR", "https://x.pdf")
    assert any(m.tipo == "INSTAURACAO_IC" for m in materias)


def test_segmentar_mprr_detecta_dispensa_licitacao():
    materias = segmentar_materias(MD_MPRR_DISPENSA_LICITACAO, "MPRR", "https://x.pdf")
    assert any(m.tipo == "DISPENSA_LICITACAO" for m in materias)


# ---------------------------------------------------------------------------
# GRUPO C — segmentar_materias (TJRR)
# ---------------------------------------------------------------------------

def test_segmentar_tjrr_detecta_emenda_regimental():
    materias = segmentar_materias(MD_TJRR_EMENDA_REGIMENTAL, "TJRR", "https://x.pdf")
    assert any(m.tipo == "EMENDA_REGIMENTAL" for m in materias)
    m = next(m for m in materias if m.tipo == "EMENDA_REGIMENTAL")
    assert "TP N. 15" in m.texto or "N. 15" in m.texto


def test_segmentar_tjrr_detecta_portaria_item():
    materias = segmentar_materias(MD_TJRR_PORTARIA_ITEM, "TJRR", "https://x.pdf")
    assert any(m.tipo == "PORTARIA_ITEM" for m in materias)


def test_segmentar_tjrr_detecta_extrato_contrato():
    materias = segmentar_materias(MD_TJRR_EXTRATO_CONTRATO, "TJRR", "https://x.pdf")
    assert any(m.tipo == "EXTRATO_CONTRATO" for m in materias)


# ---------------------------------------------------------------------------
# GRUPO D — Casos de borda
# ---------------------------------------------------------------------------

def test_markdown_vazio_retorna_lista_vazia():
    materias = segmentar_materias("", "MPRR", "https://x.pdf")
    assert materias == []


def test_markdown_sem_padroes_conhecidos_retorna_lista_vazia():
    md = "###### **ALGO ALEATÓRIO**\n\nTexto sem padrão editorial relevante."
    materias = segmentar_materias(md, "MPRR", "https://x.pdf")
    assert materias == []


def test_orgao_invalido_levanta_valueerror():
    with pytest.raises(ValueError, match="orgao"):
        segmentar_materias("conteudo", "FOO", "https://x.pdf")


def test_orgao_mprr_ignora_padroes_tjrr():
    materias = segmentar_materias(MD_TJRR_EMENDA_REGIMENTAL, "MPRR", "https://x.pdf")
    assert all(m.tipo != "EMENDA_REGIMENTAL" for m in materias)


# ---------------------------------------------------------------------------
# GRUPO E — Markdown com múltiplas matérias
# ---------------------------------------------------------------------------

def test_segmentar_markdown_com_multiplas_materias_mprr():
    md = MD_MPRR_ATO_PGJ + "\n\n" + MD_MPRR_EXTRATO_CONTRATO
    materias = segmentar_materias(md, "MPRR", "https://x.pdf")
    tipos = {m.tipo for m in materias}
    assert "ATO_PGJ" in tipos
    assert "EXTRATO_CONTRATO" in tipos


# ---------------------------------------------------------------------------
# GRUPO E — Markdown com múltiplas matérias (continuação)
# ---------------------------------------------------------------------------

def test_segmentar_materias_isoladas_nao_vazam_texto():
    """Garante que matérias separadas no Markdown não compartilham texto.

    Falha cedo se a implementação retornar o Markdown inteiro N vezes
    (uma por padrão casado) em vez de fatiar corretamente.
    """
    md = MD_MPRR_ATO_PGJ + "\n\n" + MD_MPRR_EXTRATO_CONTRATO
    materias = segmentar_materias(md, "MPRR", "https://x.pdf")

    ato = next(m for m in materias if m.tipo == "ATO_PGJ")
    extrato = next(m for m in materias if m.tipo == "EXTRATO_CONTRATO")

    # Texto do ATO não deve incluir conteúdo do EXTRATO
    assert "EMPRESA EXEMPLO" not in ato.texto
    assert "429.000" not in ato.texto

    # E vice-versa
    assert "REMOVER" not in extrato.texto
    assert "MARIA DA SILVA" not in extrato.texto
