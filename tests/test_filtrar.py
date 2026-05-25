"""Testes do filtro de ruído em matérias (Ciclos 8.5 + 10.5b).

Taxonomia de tipos alinhada ao Ciclo 10.5a (segmentar): famílias MPRR
PORTARIA / EXTRATO / AVISO + tipos TJRR (EMENDA_REGIMENTAL, PORTARIA_ITEM,
EXTRATO_CONTRATO). Regras de relevância (10.5b):
- EXTRATO e AVISO (gasto/licitação) + EMENDA_REGIMENTAL → sempre relevantes.
- PORTARIA (mistura atos PGJ com DG administrativo) → exige sinal forte.
- INSTAURAÇÃO é sinal forte (preserva instaurações que vêm como PORTARIA).
"""

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
    assert filtrar_materias([]) == []


def test_funcao_e_pura_nao_modifica_entrada():
    original = [
        _m("PORTARIA", "REMOVER, a pedido, a Procuradora..."),
        _m("EXTRATO", "licença para tratamento de saúde..."),
    ]
    copia = list(original)
    filtrar_materias(original)
    assert original == copia
    assert original[0].tipo == "PORTARIA"
    assert original[1].tipo == "EXTRATO"


# ---------------------------------------------------------------------------
# GRUPO B — Sinais de descarte (vencem sempre, mesmo tipo sempre-relevante)
# ---------------------------------------------------------------------------

def test_sinal_descarte_licenca_saude_filtra():
    mat = _m("EXTRATO", "Contrato celebrado, com licença para tratamento de saúde...")
    assert filtrar_materias([mat]) == []


def test_sinal_descarte_convalidar_licenca_filtra():
    mat = _m("PORTARIA", "Convalidar a licença anterior do servidor...")
    assert filtrar_materias([mat]) == []


def test_sinal_descarte_conceder_ferias_filtra():
    mat = _m("PORTARIA", "Conceder 30 dias de férias ao servidor...")
    assert filtrar_materias([mat]) == []


def test_sinal_descarte_folga_plantoes_sem_virgula_filtra():
    """Texto real (MPRR ed. 951): 'folga em razão de plantões' SEM vírgula."""
    mat = _m(
        "PORTARIA",
        "Conceder ao Promotor de Justiça, Dr. PAULO ANDRÉ DE CAMPOS "
        "TRINDADE, 01 (um) dia de folga em razão de plantões "
        "ministeriais a ser usufruído em 19JUN2026.",
    )
    assert filtrar_materias([mat]) == []


def test_sinal_descarte_vence_tipo_sempre_relevante():
    """Descarte tem precedência mesmo sobre EXTRATO (sempre relevante)."""
    mat = _m("EXTRATO", "EXTRATO ... com licença maternidade da servidora ...")
    assert filtrar_materias([mat]) == []


# ---------------------------------------------------------------------------
# GRUPO C — Tipos sempre relevantes (EXTRATO, AVISO, EMENDA_REGIMENTAL)
# ---------------------------------------------------------------------------

def test_extrato_sempre_relevante_sem_sinal():
    """Qualquer EXTRATO (gasto/tramitação) passa sem precisar de sinal forte."""
    mat = _m("EXTRATO", "EXTRATO DE NOTA DE EMPENHO\nValor: R$ 12.000,00")
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1
    assert resultado[0].tipo == "EXTRATO"


def test_aviso_sempre_relevante_sem_sinal():
    """Licitações (AVISO) passam sem precisar de sinal forte."""
    mat = _m("AVISO", "AVISO DE LICITAÇÃO\nObjeto: aquisição de mobiliário.")
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1
    assert resultado[0].tipo == "AVISO"


def test_emenda_regimental_passa():
    mat = _m("EMENDA_REGIMENTAL", "Altera o Regimento Interno...", orgao="TJRR")
    assert len(filtrar_materias([mat])) == 1


# ---------------------------------------------------------------------------
# GRUPO D — PORTARIA exige sinal forte
# ---------------------------------------------------------------------------

def test_portaria_com_remover_pedido_passa():
    mat = _m("PORTARIA", "REMOVER, a pedido, a Procuradora MARIA DA SILVA...")
    assert len(filtrar_materias([mat])) == 1


def test_portaria_com_instauracao_passa():
    """Instauração de investigação é alto valor mesmo vindo como PORTARIA."""
    mat = _m(
        "PORTARIA",
        "PORTARIA Nº 018/2026 – MP/PJ – DE INSTAURAÇÃO DO PA Nº 013/2026.",
    )
    resultado = filtrar_materias([mat])
    assert len(resultado) == 1


def test_portaria_com_apurar_improbidade_passa():
    mat = _m("PORTARIA", "Instaurar procedimento para apurar improbidade administrativa...")
    assert len(filtrar_materias([mat])) == 1


# ---------------------------------------------------------------------------
# GRUPO E — PORTARIA sem sinal forte é filtrada
# ---------------------------------------------------------------------------

def test_portaria_sem_sinal_forte_filtra():
    mat = _m("PORTARIA", "Designar substituto eventual para a função gratificada.")
    assert filtrar_materias([mat]) == []


def test_portaria_item_tjrr_sem_sinal_filtra():
    mat = _m(
        "PORTARIA_ITEM",
        "N. 1 - Designar substituto eventual sem prejuízo...",
        orgao="TJRR",
    )
    assert filtrar_materias([mat]) == []


# ---------------------------------------------------------------------------
# GRUPO F — Mistura de matérias
# ---------------------------------------------------------------------------

def test_mistura_filtra_corretamente():
    materias = [
        _m("PORTARIA", "REMOVER, a pedido, a Procuradora..."),     # sinal forte
        _m("PORTARIA", "licença saúde, convalidar..."),            # descarte
        _m("EXTRATO", "EXTRATO DE NOTA DE EMPENHO\nR$ 5.000,00"),  # sempre relevante
        _m("AVISO", "AVISO DE REABERTURA DE LICITAÇÃO..."),        # sempre relevante
        _m("PORTARIA", "Designar substituto temporário..."),       # sem sinal → fora
        _m("EMENDA_REGIMENTAL", "Altera regimento...", orgao="TJRR"),
    ]
    resultado = filtrar_materias(materias)
    tipos = [m.tipo for m in resultado]
    assert len(resultado) == 4
    assert tipos.count("PORTARIA") == 1
    assert "EXTRATO" in tipos
    assert "AVISO" in tipos
    assert "EMENDA_REGIMENTAL" in tipos


# ---------------------------------------------------------------------------
# GRUPO G — Robustez
# ---------------------------------------------------------------------------

def test_sinais_sao_case_insensitive():
    mat_descarte = _m("PORTARIA", "licença Para Tratamento De SAÚDE...")
    assert filtrar_materias([mat_descarte]) == []
    mat_forte = _m("PORTARIA", "de instauração do inquérito civil")
    assert len(filtrar_materias([mat_forte])) == 1


def test_extrato_funciona_com_markdown_formatado():
    mat = _m("EXTRATO", "**EXTRATO DA PORTARIA DE ARQUIVAMENTO PA SIMP Nº 1/24**\n\nDetalhes...")
    assert len(filtrar_materias([mat])) == 1
