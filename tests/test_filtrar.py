"""Testes do filtro de ruído em matérias (Ciclo 8.5)."""

from __future__ import annotations

from scripts.filtrar import filtrar_materias
from scripts.segmentar import Materia


def _m(tipo: str, texto: str, orgao: str = "MPRR") -> Materia:
    return Materia(
        orgao=orgao,
        tipo=tipo,
        texto=texto,
        pdf_url="https://example.com/x.pdf",
    )


# ---------------------------------------------------------------------------
# GRUPO A — Função pura e lista vazia
# ---------------------------------------------------------------------------

def test_lista_vazia_retorna_lista_vazia():
    resultado = filtrar_materias([])
    assert resultado == []


def test_funcao_e_pura_nao_modifica_entrada():
    original = [
        _m("ATO_PGJ", "REMOVER, a pedido, a Procuradora..."),
        _m("EXTRATO_CONTRATO", "licença para tratamento de saúde..."),
    ]
    copia = list(original)
    filtrar_materias(original)
    assert original == copia
    assert original[0].tipo == "ATO_PGJ"
    assert original[1].tipo == "EXTRATO_CONTRATO"


# ---------------------------------------------------------------------------
# GRUPO B — Sinais de descarte (filtragem)
# ---------------------------------------------------------------------------

def test_sinal_descarte_licenca_saude_filtra():
    mat = _m(
        "EXTRATO_CONTRATO",
        "Contrato celebrado, com licença para tratamento de saúde...",
    )
    resultado = filtrar_materias([mat])
    assert resultado == []


def test_sinal_descarte_convalidar_licenca_filtra():
    mat = _m("ATO_PGJ", "Convalidar a licença anterior do servidor...")
    resultado = filtrar_materias([mat])
    assert resultado == []


def test_sinal_descarte_conceder_ferias_filtra():
    mat = _m("ATO_PGJ", "Conceder 30 dias de férias ao servidor...")
    resultado = filtrar_materias([mat])
    assert resultado == []


# ---------------------------------------------------------------------------
# GRUPO C — Tipos sempre relevantes
# ---------------------------------------------------------------------------

def test_ato_pgj_sem_sinal_forte_passa():
    mat = _m("ATO_PGJ", "REMOVER, a pedido, a Procuradora MARIA DA SILVA...")
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1
    assert resultado[0].tipo == "ATO_PGJ"


def test_emenda_regimental_passa():
    mat = _m(
        "EMENDA_REGIMENTAL",
        "Altera o Regimento Interno...",
        orgao="TJRR",
    )
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1


def test_dispensa_licitacao_passa():
    mat = _m(
        "DISPENSA_LICITACAO",
        "Contratado fornecedor para fornecimento...",
    )
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1


def test_instauracao_ic_passa():
    mat = _m(
        "INSTAURACAO_IC",
        "Instauração de inquérito civil para apurar...",
    )
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1


# ---------------------------------------------------------------------------
# GRUPO D — Tipos ambíguos com sinal forte
# ---------------------------------------------------------------------------

def test_extrato_contrato_com_sinal_forte_passa():
    mat = _m(
        "EXTRATO_CONTRATO",
        "EXTRATO DE CONTRATO N. 25/2026\nVALOR R$ 100.000,00",
    )
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1


def test_portaria_item_com_sinal_remover_pedido_passa():
    mat = _m(
        "PORTARIA_ITEM",
        "PORTARIA TJRR/PR — REMOVER, a pedido, o servidor...",
        orgao="TJRR",
    )
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1


# ---------------------------------------------------------------------------
# GRUPO E — Tipos ambíguos sem sinal forte
# ---------------------------------------------------------------------------

def test_extrato_contrato_sem_sinal_forte_filtra():
    mat = _m(
        "EXTRATO_CONTRATO",
        "Conteúdo sem indicação clara de contrato relevante.",
    )
    resultado = filtrar_materias([mat])
    assert resultado == []


def test_portaria_item_sem_sinal_forte_filtra():
    mat = _m(
        "PORTARIA_ITEM",
        "N. 1 - Designar substituto eventual sem prejuízo...",
        orgao="TJRR",
    )
    resultado = filtrar_materias([mat])
    assert resultado == []


# ---------------------------------------------------------------------------
# GRUPO F — Mistura de matérias
# ---------------------------------------------------------------------------

def test_mistura_filtra_corretamente():
    materias = [
        _m("ATO_PGJ", "REMOVER, a pedido, a Procuradora..."),
        _m("EXTRATO_CONTRATO", "licença saúde, convalidar..."),
        _m("EXTRATO_CONTRATO", "EXTRATO DE CONTRATO N. 5/2026..."),
        _m("PORTARIA_ITEM", "Designar substituto temporário..."),
        _m("EMENDA_REGIMENTAL", "Altera regimento...", orgao="TJRR"),
    ]
    resultado = filtrar_materias(materias)
    assert len(resultado) == 3
    tipos = [m.tipo for m in resultado]
    assert "ATO_PGJ" in tipos
    assert "EXTRATO_CONTRATO" in tipos
    assert "EMENDA_REGIMENTAL" in tipos


# ---------------------------------------------------------------------------
# GRUPO G — Robustez
# ---------------------------------------------------------------------------

def test_sinais_sao_case_insensitive():
    mat_descarte = _m("ATO_PGJ", "licença Para Tratamento De SAÚDE...")
    assert filtrar_materias([mat_descarte]) == []
    mat_forte = _m("EXTRATO_CONTRATO", "extrato do contrato n. 10/2026")
    assert len(filtrar_materias([mat_forte])) == 1


def test_sinais_funcionam_com_markdown_formatado():
    mat = _m(
        "EXTRATO_CONTRATO",
        "**EXTRATO DE CONTRATO N. 25/2026**\n\nDetalhes...",
    )
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1
