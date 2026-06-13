"""Testes do filtro sensível por página (bloqueador da Sessão 12).

`pagina_sensivel(texto) -> str | None` avalia o texto INTEGRAL de uma
página de diário e devolve o nome da regra que casou (ou None). É o
funil único do índice: aplicado no /indexar, sobrevive a reindexações
por construção.

Diferença deliberada para o validador editorial da Fase 3: texto
integral de diário oficial cita vocabulário jurídico o tempo todo,
então aqui só entram regras de ALTA PRECISÃO — o risco do ECA art. 143
é a IDENTIFICABILIDADE do menor, e cada regra exige a combinação de
contexto sensível + identificador (termo de menor, idade exata,
iniciais).
"""

import pytest

from app.filtro_sensivel import pagina_sensivel

# ---------------------------------------------------------------------------
# Regra 1 — crime sexual + termo de menor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "instaurar procedimento para apurar estupro de vulnerável praticado contra criança",
        "investigação de abuso sexual envolvendo adolescente da comarca",
        "exploração sexual de menor de idade no município",
        "denúncia por importunação sexual contra adolescente",
    ],
)
def test_crime_sexual_com_menor_casa(texto):
    assert pagina_sensivel(texto) == "crime_sexual_menor"


def test_pornografia_infantil_casa_sozinha():
    # o termo já carrega o menor — não exige segundo identificador
    assert pagina_sensivel("apreensão de material de pornografia infantil") == (
        "crime_sexual_menor"
    )


def test_crime_sexual_sem_termo_de_menor_nao_casa():
    # vítima adulta: página segue buscável
    texto = "condenação por estupro; a vítima, maior de idade, foi ouvida em juízo"
    assert pagina_sensivel(texto) is None


def test_termo_de_menor_sem_crime_nao_casa():
    texto = "programa de contraturno escolar para crianças e adolescentes do bairro"
    assert pagina_sensivel(texto) is None


# ---------------------------------------------------------------------------
# Regra 2 — idade exata + termo de menor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "a vítima, adolescente de 14 anos, residente na comarca de Bonfim",
        "criança de 7 anos encaminhada ao conselho tutelar",
        "menor de idade, 16 anos, apreendido em flagrante",
    ],
)
def test_idade_exata_de_menor_casa(texto):
    assert pagina_sensivel(texto) == "idade_exata_menor"


def test_idade_adulta_nao_casa():
    assert pagina_sensivel("o requerente, jovem de 19 anos, compareceu") is None
    assert pagina_sensivel("servidor com 45 anos de idade") is None


def test_menor_preco_com_prazo_em_anos_nao_casa():
    # "menor" comercial + duração de contrato não é menor de idade
    texto = "proposta de menor preço, contrato com vigência de 5 anos"
    assert pagina_sensivel(texto) is None


# ---------------------------------------------------------------------------
# Regra 3 — procedimento de família/acolhimento + iniciais anonimizadas
# ---------------------------------------------------------------------------


def test_destituicao_com_iniciais_casa():
    texto = "ação de destituição do poder familiar em face de J. da S. L., menor"
    assert pagina_sensivel(texto) == "familia_iniciais"


def test_acolhimento_com_iniciais_casa():
    texto = "acolhimento institucional da criança A. B. C. determinado pelo juízo"
    assert pagina_sensivel(texto) == "familia_iniciais"


def test_destituicao_sem_iniciais_nao_casa():
    # sem identificador não há reidentificação — página segue buscável
    texto = "audiência sobre destituição do poder familiar designada para abril"
    assert pagina_sensivel(texto) is None


def test_razao_social_com_iniciais_nao_casa():
    # falso positivo conhecido da Fase 4 (razões sociais): sem vocabulário
    # de família/acolhimento, iniciais não bastam
    texto = "extrato de contrato celebrado com J. W. Serviços Ltda para manutenção"
    assert pagina_sensivel(texto) is None


def test_adocao_de_medidas_nao_casa():
    # burocrês ("adoção de medidas") não entra na regra de família
    texto = "recomenda a adoção de medidas administrativas cabíveis J. W. S."
    assert pagina_sensivel(texto) is None


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------


def test_casa_sem_acento_e_caixa():
    assert pagina_sensivel("ESTUPRO DE VULNERAVEL CONTRA CRIANCA") == (
        "crime_sexual_menor"
    )


def test_texto_vazio_retorna_none():
    assert pagina_sensivel("") is None
