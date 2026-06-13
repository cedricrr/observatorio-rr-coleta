"""Testes do classificador de leads (módulo puro app/classificador.py).

Classifica a sessão de busca em 'tecnico' ou 'geral' a partir dos termos
buscados. Técnico = público jurídico/administrativo (advogados, servidores);
geral = cidadão buscando o próprio nome ou concursos. Empate → técnico.
"""

import pytest

from app.classificador import classificar_termos

# ---------------------------------------------------------------------------
# Regras que classificam como TÉCNICO (uma a uma)
# ---------------------------------------------------------------------------


def test_numero_cnj_e_tecnico():
    assert classificar_termos(["0801234-56.2024.8.23.0010"]) == "tecnico"


def test_numero_cnj_dentro_de_frase_e_tecnico():
    assert classificar_termos(["processo 0801234-56.2024.8.23.0010"]) == "tecnico"


def test_padrao_oab_e_tecnico():
    assert classificar_termos(["OAB/RR 1234"]) == "tecnico"


@pytest.mark.parametrize(
    "termo",
    ["intimação", "acórdão", "despacho", "sentença", "citação", "embargos"],
)
def test_vocabulario_processual_e_tecnico(termo):
    assert classificar_termos([termo]) == "tecnico"


@pytest.mark.parametrize(
    "termo",
    ["portaria", "provimento", "resolução", "designação", "remoção"],
)
def test_vocabulario_administrativo_e_tecnico(termo):
    assert classificar_termos([termo]) == "tecnico"


def test_tres_nomes_distintos_na_sessao_e_tecnico():
    termos = ["João da Silva", "Maria Souza Lima", "Pedro Alcântara"]
    assert classificar_termos(termos) == "tecnico"


# ---------------------------------------------------------------------------
# Casos GERAL
# ---------------------------------------------------------------------------


def test_nome_proprio_isolado_e_geral():
    assert classificar_termos(["João da Silva"]) == "geral"


def test_dois_nomes_distintos_ainda_e_geral():
    assert classificar_termos(["João da Silva", "Maria Souza Lima"]) == "geral"


def test_mesmo_nome_repetido_nao_conta_como_distinto():
    termos = ["João da Silva", "joão da silva", "JOÃO DA SILVA"]
    assert classificar_termos(termos) == "geral"


@pytest.mark.parametrize("termo", ["concurso público", "edital de concurso"])
def test_vocabulario_de_concurso_e_geral(termo):
    assert classificar_termos([termo]) == "geral"


def test_sequencia_de_11_digitos_e_geral():
    # CPF digitado puro não indica usuário técnico
    assert classificar_termos(["12345678901"]) == "geral"


def test_lista_vazia_e_geral():
    assert classificar_termos([]) == "geral"


# ---------------------------------------------------------------------------
# Desempate e robustez de entrada
# ---------------------------------------------------------------------------


def test_empate_resolve_para_tecnico():
    # sinal geral (nome isolado) + sinal técnico (vocabulário processual)
    assert classificar_termos(["João da Silva", "intimação"]) == "tecnico"


def test_vocabulario_casa_sem_acento_e_caixa():
    # usuário de busca digita sem acento; o classificador não pode exigi-lo
    assert classificar_termos(["INTIMACAO"]) == "tecnico"
    assert classificar_termos(["Acordao"]) == "tecnico"


def test_vocabulario_nao_casa_por_substring_de_palavra():
    # "sentença" não pode casar dentro de "apresentação" nem
    # "citação" dentro de "licitação" (palavra inteira)
    assert classificar_termos(["apresentação de empresa"]) == "geral"
    assert classificar_termos(["licitação"]) == "geral"
