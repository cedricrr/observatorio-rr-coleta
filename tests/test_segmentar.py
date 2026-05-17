"""Testes do segmentador de matérias sobre Markdown (Ciclo 8.4)."""

from __future__ import annotations

import pytest

from scripts.segmentar import Materia, segmentar_materias


# ---------------------------------------------------------------------------
# Fixtures de Markdown — formato REAL pós-refactor 2026-05-17
# (extraídos de /tmp/mprr_real.md, diário 951 do MPRR)
# ---------------------------------------------------------------------------

MD_MPRR_PORTARIA_PGJ = """
Boa Vista, 30 de abril de 2026                         Edição 951                                  4


**PORTARIA - Nº 1125662 - PGJ, 29 DE ABRIL DE 2026**


O **PROCURADOR-GERAL DE JUSTIÇA DO MINISTÉRIO PÚBLICO DO ESTADO DE RORAIMA**,
com fulcro na última parte do inciso IX, art. 12; e art. 139, ambos da Lei Complementar nº 003/1994;


**CONSIDERANDO** a remoção da Procuradora de Justiça, Dra. **JANAÍNA CARNEIRO COSTA**,
conforme Ato nº 025-PGJ, de 27ABR2026, publicado no DEMPRR nº 949, de 28ABR2026;


**R E S O L V E :**

Convocar, _ad referendum_ do Conselho Superior do Ministério Público, o Promotor de Justiça
de segunda entrância, Dr. **ADEMAR LOIOLA MOTA**, para responder pela 6ª Procuradoria de Justiça
Criminal, com prejuízo de suas funções originárias.
"""


MD_MPRR_INSTAURACAO_IC = """
# **PROMOTORIA DE JUSTIÇA DA COMARCA DE SÃO LUIZ DO ANAUÁ**


**PORTARIA Nº 022/2026 – MP/PJ/SLA – DE INSTAURAÇÃO DO PA Nº 17/2026 – SIMP Nº 000418-**

**060/2026**


O **MINISTÉRIO PÚBLICO DO ESTADO DE RORAIMA**, por intermédio da Promotora de Justiça
Substituta da Promotoria de Justiça da Comarca de São Luiz do Anauá, no exercício das atribuições
institucionais conferidas pelo artigo 129, da Constituição Federal.
"""


MD_MPRR_EXTRATO_CONTRATO = """
| B o a V i s t a , 3 0 d e a b r i l d e 2 0 2 6 Edição 951 25<br>EXTRATO DO CONTRATO Nº 34/2026 – PROCESSO SEI Nº 19.26.1000000.0002608/2026-64<br>A Seção de Compras e Contratos do Ministério Público do Estado de Roraima, em cumprimento ao art.<br>37 da CF/88, vem tornar público o resumo do Contrato nº 34/2026.<br>OBJETO: Aquisição de suprimentos de informática.<br>CONTRATADA: 29.127.173 FAYRLON GUEDES SOARES.<br>VALOR: R$ 1.590,00 (um mil, quinhentos e noventa reais).
"""


MD_MPRR_DISPENSA_LICITACAO = """
| Edição 951 26<br>EXTRATO DE DISPENSA DE LICITAÇÃO Nº 05/2026<br>PROCESSO SEI Nº 19.26.1000000.0002608/2026-64<br>CONTRATADO: FORNECEDOR LTDA<br>OBJETO: instalação de cerca eletrificada na nova Promotoria<br>VALOR: R$ 35.000,00<br>Fundamentação: art. 75, II, Lei 14.133/2021.
"""


MD_MPRR_TERMO_ADITIVO = """
| Edição 951 27<br>EXTRATO DE TERMO ADITIVO AO CONTRATO Nº 12/2025<br>PROCESSO SEI Nº 19.26.1000000.0001234/2025-99<br>OBJETO: prorrogação de vigência por mais 12 meses.<br>VALOR: R$ 50.000,00 (cinquenta mil reais).
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
        tipo="PORTARIA_PGJ",
        texto="conteudo",
        pdf_url="https://example.com/a.pdf",
    )
    assert m.orgao == "MPRR"
    assert m.tipo == "PORTARIA_PGJ"
    assert m.texto == "conteudo"
    assert m.pdf_url == "https://example.com/a.pdf"
    assert m.pagina is None


def test_materia_aceita_pagina_opcional():
    m = Materia(
        orgao="MPRR",
        tipo="PORTARIA_PGJ",
        texto="x",
        pdf_url="y",
        pagina=5,
    )
    assert m.pagina == 5


# ---------------------------------------------------------------------------
# GRUPO B — segmentar_materias (MPRR) — formato REAL pós-refactor 17/05
# ---------------------------------------------------------------------------

def test_segmentar_mprr_detecta_portaria_pgj():
    materias = segmentar_materias(MD_MPRR_PORTARIA_PGJ, "MPRR", "https://test.pdf")
    assert len(materias) >= 1
    assert any(m.tipo == "PORTARIA_PGJ" for m in materias)
    m = next(m for m in materias if m.tipo == "PORTARIA_PGJ")
    assert m.orgao == "MPRR"
    assert "Convocar" in m.texto or "ADEMAR" in m.texto
    assert m.pdf_url == "https://test.pdf"


def test_segmentar_mprr_detecta_instauracao_ic():
    materias = segmentar_materias(MD_MPRR_INSTAURACAO_IC, "MPRR", "https://x.pdf")
    assert any(m.tipo == "INSTAURACAO_IC" for m in materias)
    m = next(m for m in materias if m.tipo == "INSTAURACAO_IC")
    assert "022/2026" in m.texto or "INSTAURAÇÃO" in m.texto


def test_segmentar_mprr_detecta_extrato_contrato_em_tabela():
    """Extrato de contrato no MPRR vem dentro de tabela Markdown
    (com pipes e <br>), SEM cercadura **.
    """
    materias = segmentar_materias(MD_MPRR_EXTRATO_CONTRATO, "MPRR", "https://x.pdf")
    assert any(m.tipo == "EXTRATO_CONTRATO" for m in materias)
    m = next(m for m in materias if m.tipo == "EXTRATO_CONTRATO")
    assert "34/2026" in m.texto or "1.590" in m.texto


def test_segmentar_mprr_detecta_dispensa_licitacao():
    materias = segmentar_materias(MD_MPRR_DISPENSA_LICITACAO, "MPRR", "https://x.pdf")
    assert any(m.tipo == "DISPENSA_LICITACAO" for m in materias)


def test_segmentar_mprr_detecta_termo_aditivo():
    """TERMO_ADITIVO é tipo novo descoberto no refactor de 17/05."""
    materias = segmentar_materias(MD_MPRR_TERMO_ADITIVO, "MPRR", "https://x.pdf")
    assert any(m.tipo == "TERMO_ADITIVO" for m in materias)


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
    md = MD_MPRR_PORTARIA_PGJ + "\n\n" + MD_MPRR_EXTRATO_CONTRATO
    materias = segmentar_materias(md, "MPRR", "https://x.pdf")
    tipos = {m.tipo for m in materias}
    assert "PORTARIA_PGJ" in tipos
    assert "EXTRATO_CONTRATO" in tipos


# ---------------------------------------------------------------------------
# GRUPO E — Markdown com múltiplas matérias (continuação)
# ---------------------------------------------------------------------------

def test_segmentar_materias_isoladas_nao_vazam_texto():
    """Garante que matérias separadas no Markdown não compartilham texto.

    Falha cedo se a implementação retornar o Markdown inteiro N vezes
    (uma por padrão casado) em vez de fatiar corretamente.
    """
    md = MD_MPRR_PORTARIA_PGJ + "\n\n" + MD_MPRR_EXTRATO_CONTRATO
    materias = segmentar_materias(md, "MPRR", "https://x.pdf")

    portaria = next(m for m in materias if m.tipo == "PORTARIA_PGJ")
    extrato = next(m for m in materias if m.tipo == "EXTRATO_CONTRATO")

    # Texto da PORTARIA não deve incluir conteúdo do EXTRATO
    assert "FAYRLON" not in portaria.texto
    assert "1.590" not in portaria.texto

    # E vice-versa
    assert "ADEMAR" not in extrato.texto
    assert "JANAÍNA" not in extrato.texto


# ---------------------------------------------------------------------------
# GRUPO H — Campos de classificação opcionais (Sub-ciclo 8.6a)
# ---------------------------------------------------------------------------

def test_materia_defaults_dos_campos_de_classificacao():
    """Materia criada sem campos de classificação tem defaults seguros."""
    m = Materia(
        orgao="MPRR",
        tipo="PORTARIA_PGJ",
        texto="x",
        pdf_url="y",
    )
    assert m.categoria is None
    assert m.manchete is None
    assert m.resumo is None
    assert m.valor_rs is None
    assert m.tags == []
    assert m.relevante is False


def test_materia_aceita_campos_de_classificacao_completos():
    """Todos os 6 campos novos podem ser passados explicitamente."""
    m = Materia(
        orgao="MPRR",
        tipo="EXTRATO_CONTRATO",
        texto="conteúdo da matéria",
        pdf_url="https://example.com/x.pdf",
        categoria="Contratos e licitações",
        manchete="MPRR contrata caminhão médio por R$ 429 mil",
        resumo="O Ministério Público formaliza compra de veículo...",
        valor_rs=429000.00,
        tags=["frota", "logística"],
        relevante=True,
    )
    assert m.categoria == "Contratos e licitações"
    assert m.manchete == "MPRR contrata caminhão médio por R$ 429 mil"
    assert m.resumo == "O Ministério Público formaliza compra de veículo..."
    assert m.valor_rs == 429000.00
    assert m.tags == ["frota", "logística"]
    assert m.relevante is True


def test_materia_tags_default_e_lista_independente():
    """Cada Materia tem sua própria lista de tags (não compartilhada)."""
    m1 = Materia(orgao="MPRR", tipo="PORTARIA_PGJ", texto="x", pdf_url="y")
    m2 = Materia(orgao="MPRR", tipo="PORTARIA_PGJ", texto="x", pdf_url="y")

    m1.tags.append("frota")

    assert m1.tags == ["frota"]
    assert m2.tags == []


def test_materia_classificada_compativel_com_segmentar_materias():
    """Backward compat: segmentar_materias produz Materia com defaults
    seguros nos campos de classificação (que serão preenchidos depois
    no Sub-ciclo 8.6c).
    """
    materias = segmentar_materias(MD_MPRR_PORTARIA_PGJ, "MPRR", "https://x.pdf")
    assert len(materias) >= 1
    m = materias[0]
    assert m.categoria is None
    assert m.manchete is None
    assert m.resumo is None
    assert m.valor_rs is None
    assert m.tags == []
    assert m.relevante is False
