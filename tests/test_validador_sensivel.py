"""Testes do validador determinístico de termos sensíveis (Fase 3 do
incidente 2026-06-10 — proteção a menores, ECA art. 143).

Camada de defesa em profundidade: NÃO depende do RLM acertar. Os testes
cobrem termos sensíveis individuais, casos de controle (matéria normal
não é alterada — inclusive armadilhas de falso positivo como "menor
preço" e "adoção de medidas"), idempotência e pureza.
"""

from __future__ import annotations

import dataclasses

import pytest

from scripts.classificar import CATEGORIA_PROTECAO_MENOR
from scripts.segmentar import Materia
from scripts.validador_sensivel import (
    aplicar_filtro_sensivel,
    casar_termo_sensivel,
)


def _materia(
    texto: str = "EXTRATO DE CONTRATO N. 25/2026 — manutenção predial.",
    resumo: str | None = "Contrato de manutenção predial firmado pelo MPRR.",
    manchete: str | None = "MPRR contrata manutenção predial",
    relevante: bool = True,
) -> Materia:
    return Materia(
        orgao="MPRR",
        tipo="EXTRATO",
        texto=texto,
        pdf_url="https://example.com/x.pdf",
        categoria="Contratos e licitações",
        manchete=manchete,
        resumo=resumo,
        valor_rs=100000.0,
        tags=["contrato"],
        relevante=relevante,
    )


def _assert_bloqueada(m: Materia) -> None:
    assert m.relevante is False
    assert m.categoria == CATEGORIA_PROTECAO_MENOR
    assert m.manchete == ""
    assert m.resumo == ""
    assert m.tags == []
    assert m.valor_rs is None


# ---------------------------------------------------------------------------
# GRUPO A — Termos sensíveis individuais (no texto)
# ---------------------------------------------------------------------------

TEXTOS_SENSIVEIS = [
    "Apurar suposto crime de estupro de vulnerável na comarca.",
    "Procedimento para apurar ESTUPRO em contexto familiar.",
    "Investigação de abuso sexual infantil em escola municipal.",
    "Apurar exploração sexual de adolescentes na região.",
    "Inquérito sobre pornografia infantil em rede social.",
    "Apurar importunação sexual de menor em transporte escolar.",
    "Acompanhar situação de vulnerabilidade de adolescente na comarca.",
    "Criança em situação de vulnerabilidade social acompanhada pelo MP.",
    "Acompanhar adolescente de 13 anos grávida na comarca de Bonfim.",
    "Medida protetiva em favor de criança de 7 anos no município.",
    "Procedimento em favor da criança J. da S. L., nascida em 2019.",
    "Acompanhamento do menor M. K. pela promotoria da comarca.",
    "Processo de adoção envolvendo criança da comarca de Pacaraima.",
    "Destituição do poder familiar requerida pelo Ministério Público.",
    "Guarda provisória de adolescente deferida em favor dos avós.",
    "Violência física contra criança em contexto familiar apurada.",
    "Autos que tramitam em segredo de justiça na vara da infância.",
]


@pytest.mark.parametrize("texto", TEXTOS_SENSIVEIS)
def test_texto_sensivel_forca_relevante_false(texto):
    m = aplicar_filtro_sensivel(_materia(texto=texto))
    _assert_bloqueada(m)


@pytest.mark.parametrize("texto", TEXTOS_SENSIVEIS)
def test_casar_termo_sensivel_identifica_termo(texto):
    termo = casar_termo_sensivel(_materia(texto=texto))
    assert termo is not None
    assert isinstance(termo, str) and termo


# ---------------------------------------------------------------------------
# GRUPO B — Campos além do texto (resumo gerado pelo RLM e manchete)
# ---------------------------------------------------------------------------

def test_termo_no_resumo_bloqueia_mesmo_com_texto_limpo():
    m = aplicar_filtro_sensivel(_materia(
        texto="EXTRATO DA PORTARIA PA SIMP Nº 1/2026 — instauração.",
        resumo="Procedimento apura estupro de vulnerável em Bonfim.",
    ))
    _assert_bloqueada(m)


def test_termo_na_manchete_bloqueia():
    m = aplicar_filtro_sensivel(_materia(
        texto="EXTRATO DA PORTARIA PA SIMP Nº 1/2026 — instauração.",
        manchete="MP apura abuso sexual infantil em Mucajaí",
    ))
    _assert_bloqueada(m)


def test_resumo_none_nao_quebra():
    m = aplicar_filtro_sensivel(_materia(resumo=None, manchete=None))
    assert m.relevante is True


# ---------------------------------------------------------------------------
# GRUPO C — Casos de controle (não alterar matéria normal)
# ---------------------------------------------------------------------------

def test_materia_normal_nao_e_alterada():
    original = _materia()
    resultado = aplicar_filtro_sensivel(original)
    assert resultado == original
    assert resultado.relevante is True
    assert casar_termo_sensivel(original) is None


def test_menor_preco_de_licitacao_nao_bloqueia():
    """"menor" em "menor preço" é jargão de licitação, não menor de idade."""
    m = aplicar_filtro_sensivel(_materia(
        texto=(
            "AVISO DE LICITAÇÃO — pregão eletrônico, critério de julgamento "
            "menor preço global, vigência de 12 anos prorrogáveis."
        ),
    ))
    assert m.relevante is True


def test_adocao_de_medidas_administrativas_nao_bloqueia():
    """"adoção de medidas/providências" é burocrês, não adoção de menor."""
    m = aplicar_filtro_sensivel(_materia(
        texto=(
            "Recomenda a adoção de medidas administrativas para regularizar "
            "o contrato de limpeza no prazo de 30 dias."
        ),
    ))
    assert m.relevante is True


def test_sigla_de_empresa_sa_nao_bloqueia():
    """"S.A." (sociedade anônima, sem espaço) não é iniciais de pessoa."""
    m = aplicar_filtro_sensivel(_materia(
        texto="Contrato com a empresa ENERGISA RORAIMA S.A. no valor anual.",
    ))
    assert m.relevante is True


def test_contrato_com_prazo_em_anos_nao_bloqueia():
    m = aplicar_filtro_sensivel(_materia(
        texto="Contrato de gestão de frota por 5 anos, R$ 1.156.215,18.",
    ))
    assert m.relevante is True


# ---------------------------------------------------------------------------
# GRUPO D — Idempotência e pureza
# ---------------------------------------------------------------------------

def test_idempotencia_aplicar_duas_vezes_nao_muda():
    uma_vez = aplicar_filtro_sensivel(_materia(texto=TEXTOS_SENSIVEIS[0]))
    duas_vezes = aplicar_filtro_sensivel(uma_vez)
    assert duas_vezes == uma_vez


def test_idempotencia_materia_normal():
    uma_vez = aplicar_filtro_sensivel(_materia())
    duas_vezes = aplicar_filtro_sensivel(uma_vez)
    assert duas_vezes == uma_vez


def test_funcao_pura_nao_modifica_entrada():
    original = _materia(texto=TEXTOS_SENSIVEIS[0])
    copia = dataclasses.replace(original)
    aplicar_filtro_sensivel(original)
    assert original == copia
    assert original.relevante is True


# ---------------------------------------------------------------------------
# GRUPO E — Robustez de matching
# ---------------------------------------------------------------------------

def test_matching_insensivel_a_acentos():
    """Texto de PDF pode perder acentos na extração."""
    m = aplicar_filtro_sensivel(_materia(
        texto="Apurar estupro de vulneravel praticado contra adolescente.",
    ))
    _assert_bloqueada(m)


def test_matching_insensivel_a_caixa():
    m = aplicar_filtro_sensivel(_materia(
        texto="APURAR ABUSO SEXUAL INFANTIL NA COMARCA.",
    ))
    _assert_bloqueada(m)


def test_iniciais_com_conectivo():
    """Padrão "X. da S. L." (iniciais com conectivo) bloqueia."""
    m = aplicar_filtro_sensivel(_materia(
        texto="Em favor de A. da S. L., representada pela genitora.",
    ))
    _assert_bloqueada(m)
