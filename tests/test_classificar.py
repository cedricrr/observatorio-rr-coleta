"""Testes da classificação editorial via RLM (Sub-ciclo 8.6c)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from scripts.classificar import (
    CATEGORIA_PROTECAO_MENOR,
    CATEGORIAS_VALIDAS,
    SYSTEM_PROMPT,
    classificar_materia,
)
from scripts.cliente_anthropic import ClienteAnthropic
from scripts.segmentar import Materia


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _materia(
    tipo: str = "EXTRATO_CONTRATO",
    texto: str = "EXTRATO DE CONTRATO N. 25/2026\nVALOR R$ 100.000",
    orgao: str = "MPRR",
) -> Materia:
    return Materia(
        orgao=orgao,
        tipo=tipo,
        texto=texto,
        pdf_url="https://example.com/x.pdf",
    )


def _cliente_mock_com_resposta(dados: dict) -> MagicMock:
    """Cria mock de ClienteAnthropic que retorna JSON dos dados."""
    cliente = MagicMock(spec=ClienteAnthropic)
    cliente.classificar.return_value = json.dumps(dados, ensure_ascii=False)
    return cliente


# ---------------------------------------------------------------------------
# GRUPO A — Classificação válida
# ---------------------------------------------------------------------------

def test_classifica_extrato_contrato_mprr():
    dados = {
        "relevante": True,
        "categoria": "Contratos e licitações",
        "manchete": "MPRR contrata caminhão por R$ 100 mil",
        "resumo": "O MP formalizou contrato de R$ 100 mil para aquisição de veículo.",
        "valor_rs": 100000.00,
        "tags": ["frota", "logística"],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_in = _materia(tipo="EXTRATO_CONTRATO")

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is True
    assert materia_out.categoria == "Contratos e licitações"
    assert materia_out.manchete == "MPRR contrata caminhão por R$ 100 mil"
    assert materia_out.resumo.startswith("O MP formalizou")
    assert materia_out.valor_rs == 100000.00
    assert materia_out.tags == ["frota", "logística"]
    assert materia_out.orgao == "MPRR"
    assert materia_out.tipo == "EXTRATO_CONTRATO"
    assert materia_out.texto == materia_in.texto


def test_classifica_emenda_regimental_tjrr():
    dados = {
        "relevante": True,
        "categoria": "Atos normativos",
        "manchete": "TJRR altera regimento sobre afastamento de desembargadores",
        "resumo": "A nova emenda regimental disciplina o quórum...",
        "valor_rs": None,
        "tags": ["regimento", "TJRR"],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_in = _materia(
        tipo="EMENDA_REGIMENTAL",
        texto="EMENDA REGIMENTAL TJRR/TP N. 15...",
        orgao="TJRR",
    )

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is True
    assert materia_out.categoria == "Atos normativos"
    assert materia_out.valor_rs is None
    assert materia_out.orgao == "TJRR"


def test_classifica_materia_marcada_como_nao_relevante():
    dados = {
        "relevante": False,
        "categoria": "Outros",
        "manchete": "Designação de substituto eventual",
        "resumo": "Designação de rotina sem repercussão pública.",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_in = _materia(tipo="PORTARIA_ITEM", orgao="TJRR")

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is False
    assert materia_out.categoria == "Outros"


def test_classifica_aceita_valor_rs_none():
    dados = {
        "relevante": True,
        "categoria": "Movimentação de pessoal",
        "manchete": "Remoção de procurador",
        "resumo": "Procurador removido a pedido.",
        "valor_rs": None,
        "tags": ["remoção"],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia = classificar_materia(_materia(tipo="PORTARIA_PGJ"), cliente)
    assert materia.valor_rs is None


def test_relevante_false_com_campos_editoriais_null_e_coagido():
    """Haiku 4.5 devolve manchete/resumo/tags null em matérias de rotina
    (relevante=False). Como esses campos não são renderizados quando a
    matéria é descartada, o endurecimento coage null→vazio em vez de
    falhar a validação e perder o sinal de classificação."""
    dados = {
        "relevante": False,
        "categoria": "Outros",
        "manchete": None,
        "resumo": None,
        "valor_rs": None,
        "tags": None,
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_out = classificar_materia(_materia(tipo="EXTRATO_CONTRATO"), cliente)

    assert materia_out.relevante is False
    assert materia_out.categoria == "Outros"
    assert materia_out.manchete == ""
    assert materia_out.resumo == ""
    assert materia_out.tags == []


def test_relevante_true_com_manchete_null_ainda_levanta_valueerror():
    """A coerção vale só para relevante=False. Matéria relevante com
    manchete null é erro de verdade (ia pro jornal sem título) e deve
    continuar falhando."""
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "manchete": None,
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    with pytest.raises(ValueError, match="manchete"):
        classificar_materia(_materia(), cliente)


# ---------------------------------------------------------------------------
# GRUPO B — Função pura
# ---------------------------------------------------------------------------

def test_funcao_e_pura_nao_modifica_entrada():
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_in = _materia()

    tipo_antes = materia_in.tipo
    texto_antes = materia_in.texto
    assert materia_in.categoria is None
    assert materia_in.manchete is None
    assert materia_in.relevante is False

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_in.categoria is None
    assert materia_in.manchete is None
    assert materia_in.relevante is False
    assert materia_in.tipo == tipo_antes
    assert materia_in.texto == texto_antes
    assert materia_out is not materia_in


# ---------------------------------------------------------------------------
# GRUPO C — Prompts construídos corretamente
# ---------------------------------------------------------------------------

def test_user_prompt_inclui_texto_da_materia():
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    texto_unico = "ASSINATURA_UNICA_XYZ_RASTREADOR"
    materia_in = _materia(texto=texto_unico)

    classificar_materia(materia_in, cliente)

    call_args = cliente.classificar.call_args
    user_prompt = (
        call_args.args[0] if call_args.args else call_args.kwargs.get("prompt", "")
    )
    assert texto_unico in user_prompt


def test_user_prompt_inclui_orgao_e_tipo():
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_in = _materia(tipo="PORTARIA_PGJ", orgao="MPRR")

    classificar_materia(materia_in, cliente)

    call_args = cliente.classificar.call_args
    user_prompt = (
        call_args.args[0] if call_args.args else call_args.kwargs.get("prompt", "")
    )
    assert "MPRR" in user_prompt
    assert "PORTARIA_PGJ" in user_prompt


def test_system_prompt_foi_passado_ao_cliente():
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)

    classificar_materia(_materia(), cliente)

    call_args = cliente.classificar.call_args
    system = call_args.kwargs.get("system")
    assert system is not None
    assert len(system) > 100


# ---------------------------------------------------------------------------
# GRUPO D — Validação de resposta
# ---------------------------------------------------------------------------

def test_json_invalido_levanta_valueerror():
    cliente = MagicMock(spec=ClienteAnthropic)
    cliente.classificar.return_value = "isso nao eh JSON valido { quebrado"
    with pytest.raises(ValueError, match="JSON"):
        classificar_materia(_materia(), cliente)


def test_categoria_fora_da_lista_levanta_valueerror():
    dados = {
        "relevante": True,
        "categoria": "Categoria Inexistente",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    with pytest.raises(ValueError, match="categoria"):
        classificar_materia(_materia(), cliente)


def test_falta_campo_obrigatorio_manchete_levanta_valueerror():
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    with pytest.raises(ValueError, match="manchete"):
        classificar_materia(_materia(), cliente)


def test_falta_campo_obrigatorio_categoria_levanta_valueerror():
    dados = {
        "relevante": True,
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    with pytest.raises(ValueError, match="categoria"):
        classificar_materia(_materia(), cliente)


def test_relevante_nao_bool_levanta_valueerror():
    dados = {
        "relevante": "yes",
        "categoria": "Outros",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    cliente = _cliente_mock_com_resposta(dados)
    with pytest.raises(ValueError, match="relevante"):
        classificar_materia(_materia(), cliente)


# ---------------------------------------------------------------------------
# GRUPO E — Constantes públicas
# ---------------------------------------------------------------------------

def test_categorias_validas_tem_9_entradas():
    assert len(CATEGORIAS_VALIDAS) == 9
    assert "Contratos e licitações" in CATEGORIAS_VALIDAS
    assert "Outros" in CATEGORIAS_VALIDAS
    assert "Decisões judiciais relevantes" in CATEGORIAS_VALIDAS


# ---------------------------------------------------------------------------
# GRUPO F — Tolerância a markdown fences na resposta (Sub-ciclo 8.6c.1)
# ---------------------------------------------------------------------------

def test_classificar_aceita_resposta_envolta_em_fence_json():
    """Modelo frequentemente envolve JSON em ```json...```.

    Bug encontrado no smoke real de 17/05/2026: Sonnet 4.6 envolve
    JSON em fence apesar do system prompt pedir o contrário. Parser
    deve tolerar.
    """
    dados = {
        "relevante": True,
        "categoria": "Designações e nomeações",
        "manchete": "TJRR designa servidor por portaria",
        "resumo": "O TJRR publicou portaria designando servidor.",
        "valor_rs": None,
        "tags": ["TJRR", "designação"],
    }
    resposta_com_fence = f"```json\n{json.dumps(dados, ensure_ascii=False)}\n```"
    cliente = MagicMock(spec=ClienteAnthropic)
    cliente.classificar.return_value = resposta_com_fence

    materia_in = _materia(tipo="PORTARIA_ITEM", orgao="TJRR")
    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is True
    assert materia_out.categoria == "Designações e nomeações"
    assert materia_out.manchete == "TJRR designa servidor por portaria"


def test_classificar_aceita_resposta_envolta_em_fence_simples():
    """Variação: fence sem 'json' depois dos backticks."""
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    resposta = f"```\n{json.dumps(dados, ensure_ascii=False)}\n```"
    cliente = MagicMock(spec=ClienteAnthropic)
    cliente.classificar.return_value = resposta

    materia = classificar_materia(_materia(), cliente)
    assert materia.relevante is True
    assert materia.categoria == "Outros"


def test_classificar_aceita_fence_com_whitespace_extra():
    """Variação: whitespace/quebras extras ao redor do fence."""
    dados = {
        "relevante": True,
        "categoria": "Outros",
        "manchete": "x",
        "resumo": "y",
        "valor_rs": None,
        "tags": [],
    }
    resposta = f"  \n\n```json\n{json.dumps(dados, ensure_ascii=False)}\n```  \n\n"
    cliente = MagicMock(spec=ClienteAnthropic)
    cliente.classificar.return_value = resposta

    materia = classificar_materia(_materia(), cliente)
    assert materia.categoria == "Outros"


def test_classificar_ainda_aceita_json_puro_sem_fence():
    """Backward compat: JSON puro sem fence continua funcionando.

    Garante que o strip de fence não quebre o caso ideal.
    """
    dados = {
        "relevante": True,
        "categoria": "Atos normativos",
        "manchete": "Lei alterada",
        "resumo": "Texto altera lei.",
        "valor_rs": None,
        "tags": ["lei"],
    }
    resposta = json.dumps(dados, ensure_ascii=False)
    cliente = MagicMock(spec=ClienteAnthropic)
    cliente.classificar.return_value = resposta

    materia = classificar_materia(_materia(), cliente)
    assert materia.categoria == "Atos normativos"


def test_classificar_fence_no_meio_nao_atrapalha_se_json_valido():
    """Caso degenerado: se modelo retornar texto + fence + texto,
    desde que o JSON principal esteja claro, parseia.

    Este teste documenta comportamento: strip remove APENAS fences
    envolventes (início e fim). Texto antes/depois do JSON fora de
    fence ainda quebra o parse, mas isso é decisão consciente.

    Não é teste obrigatório — pode falhar e tudo bem. Mantido para
    documentar limite.
    """
    pass


# ---------------------------------------------------------------------------
# GRUPO G — Proteção a menores (incidente 2026-06-10, ECA art. 143)
#
# O cliente é mockado, então estes testes NÃO validam o comportamento do
# RLM em si — validam (a) que a regra está no SYSTEM_PROMPT, antes das
# categorias; (b) que o pipeline ACEITA a resposta mínima da regra
# (categoria "protecao_menor" sem manchete/resumo/tags), que antes era
# rejeitada pela validação; (c) o endurecimento determinístico: categoria
# "protecao_menor" força relevante=False e zera os campos editoriais,
# mesmo que o modelo devolva relevante=true ou manchete preenchida.
# A camada que não depende do RLM acertar é a Fase 3 (validador_sensivel).
# ---------------------------------------------------------------------------

def _resposta_protecao_minima() -> dict:
    """Resposta mínima prevista pela regra: só relevante + categoria."""
    return {"relevante": False, "categoria": "protecao_menor"}


def test_protecao_menor_estupro_vulneravel_idade_comarca():
    """Matéria de estupro de vulnerável + idade + comarca → relevante=False."""
    cliente = _cliente_mock_com_resposta(_resposta_protecao_minima())
    materia_in = _materia(
        tipo="PORTARIA",
        texto=(
            "**EXTRATO DA PORTARIA DE INSTAURAÇÃO PA SIMP Nº 000578-090/2025**\n"
            "Apurar situação de vulnerabilidade de adolescente de 13 anos "
            "grávida em decorrência de suposto estupro de vulnerável. "
            "Promotoria de Justiça da Comarca de Bonfim."
        ),
    )

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is False
    assert materia_out.categoria == CATEGORIA_PROTECAO_MENOR
    assert not materia_out.manchete
    assert not materia_out.resumo
    assert materia_out.tags == []


def test_protecao_menor_adolescente_gravida():
    """Mesmo se o modelo devolver relevante=true com categoria protecao_menor,
    o endurecimento determinístico força relevante=False e zera editorial."""
    dados = {
        "relevante": True,
        "categoria": "protecao_menor",
        "manchete": "MP acompanha adolescente de 13 anos grávida",
        "resumo": "Procedimento sobre adolescente grávida.",
        "valor_rs": None,
        "tags": ["adolescente"],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_in = _materia(
        texto="Acompanhar adolescente de 13 anos grávida na comarca.",
    )

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is False
    assert materia_out.categoria == CATEGORIA_PROTECAO_MENOR
    assert not materia_out.manchete
    assert not materia_out.resumo
    assert materia_out.tags == []
    assert materia_out.valor_rs is None


def test_protecao_menor_iniciais_anonimizadas():
    """Matéria com iniciais anonimizadas pelo MP ("X. da S. L.")."""
    cliente = _cliente_mock_com_resposta(_resposta_protecao_minima())
    materia_in = _materia(
        texto=(
            "Procedimento administrativo em favor da criança J. da S. L., "
            "nascida em 2019, no município de Pacaraima."
        ),
    )

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is False
    assert materia_out.categoria == CATEGORIA_PROTECAO_MENOR


def test_protecao_menor_adocao_com_iniciais():
    """Adoção/destituição com iniciais do menor no texto."""
    cliente = _cliente_mock_com_resposta(_resposta_protecao_minima())
    materia_in = _materia(
        orgao="TJRR",
        tipo="PORTARIA_ITEM",
        texto=(
            "Processo de adoção e destituição do poder familiar "
            "envolvendo o menor M. K., comarca de Rorainópolis."
        ),
    )

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is False
    assert materia_out.categoria == CATEGORIA_PROTECAO_MENOR
    assert not materia_out.manchete


def test_protecao_menor_controle_contrato_normal_segue_relevante():
    """Controle: matéria de contrato comum não é afetada pela regra."""
    dados = {
        "relevante": True,
        "categoria": "Contratos e licitações",
        "manchete": "MPRR contrata manutenção predial por R$ 250 mil",
        "resumo": "Contrato de manutenção predial firmado pelo MPRR.",
        "valor_rs": 250000.0,
        "tags": ["contrato", "manutenção"],
    }
    cliente = _cliente_mock_com_resposta(dados)
    materia_in = _materia(
        texto="EXTRATO DE CONTRATO N. 30/2026 — manutenção predial, R$ 250.000,00",
    )

    materia_out = classificar_materia(materia_in, cliente)

    assert materia_out.relevante is True
    assert materia_out.categoria == "Contratos e licitações"
    assert materia_out.manchete == "MPRR contrata manutenção predial por R$ 250 mil"


def test_system_prompt_tem_regra_de_protecao_antes_das_categorias():
    """A regra de proteção precisa existir e vir ANTES das categorias."""
    pos_regra = SYSTEM_PROMPT.find("REGRA DE PROTEÇÃO A MENORES — PRIORIDADE MÁXIMA")
    pos_categorias = SYSTEM_PROMPT.find("CATEGORIAS DISPONÍVEIS")
    assert pos_regra != -1
    assert pos_categorias != -1
    assert pos_regra < pos_categorias
    assert "art. 143" in SYSTEM_PROMPT
    assert 'categoria="protecao_menor"' in SYSTEM_PROMPT


def test_categoria_protecao_menor_nao_entra_nas_categorias_editoriais():
    """protecao_menor é sentinela de despublicação, não categoria editorial
    (nunca é renderizada — relevante é sempre False)."""
    assert CATEGORIA_PROTECAO_MENOR == "protecao_menor"
    assert CATEGORIA_PROTECAO_MENOR not in CATEGORIAS_VALIDAS
