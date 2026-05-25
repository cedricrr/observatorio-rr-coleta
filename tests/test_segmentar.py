"""Testes do segmentador de matérias sobre Markdown (Ciclos 8.4 + 10.5a)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from scripts.segmentar import Materia, segmentar_materias


# ---------------------------------------------------------------------------
# Fixtures reais (Ciclo 10.5a) — Markdown congelado de edições MPRR reais,
# produzido por pdf_para_markdown a partir dos PDFs no R2. Cobrem variação
# de formato entre períodos: hífen antes do "Nº" opcional, sufixos PGJ/DG/DA,
# família EXTRATO ampla (empenho, termo aditivo, da portaria) e AVISO de
# licitação. Ver [[project_bug_padroes_mprr_markdown_real]].
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture(nome: str) -> str:
    return (FIXTURES_DIR / nome).read_text(encoding="utf-8")


def _contagem(materias: list[Materia]) -> dict[str, int]:
    return dict(Counter(m.tipo for m in materias))


# Cabeçalho MPRR em formato REAL (bold-wrapped), usado em testes de
# backward-compat que não precisam de uma edição inteira.
MD_MPRR_PORTARIA_PGJ = """
Boa Vista, 30 de abril de 2026                         Edição 951                                  4


**PORTARIA - Nº 1125662 - PGJ, 29 DE ABRIL DE 2026**


O **PROCURADOR-GERAL DE JUSTIÇA DO MINISTÉRIO PÚBLICO DO ESTADO DE RORAIMA**,
com fulcro na última parte do inciso IX, art. 12; e art. 139, ambos da Lei Complementar nº 003/1994;


**R E S O L V E :**

Convocar, _ad referendum_ do Conselho Superior do Ministério Público, o Promotor de Justiça
de segunda entrância, Dr. **ADEMAR LOIOLA MOTA**, para responder pela 6ª Procuradoria.
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
        tipo="PORTARIA",
        texto="conteudo",
        pdf_url="https://example.com/a.pdf",
    )
    assert m.orgao == "MPRR"
    assert m.tipo == "PORTARIA"
    assert m.texto == "conteudo"
    assert m.pdf_url == "https://example.com/a.pdf"
    assert m.pagina is None


def test_materia_aceita_pagina_opcional():
    m = Materia(
        orgao="MPRR",
        tipo="PORTARIA",
        texto="x",
        pdf_url="y",
        pagina=5,
    )
    assert m.pagina == 5


# ---------------------------------------------------------------------------
# GRUPO B — segmentar_materias (MPRR) contra fixtures REAIS — 3 famílias
# (Ciclo 10.5a). Famílias: PORTARIA, EXTRATO, AVISO. Limiares com margem
# abaixo das contagens medidas, para não ficarem frágeis a pequenas
# variações de extração entre versões do pymupdf4llm.
# ---------------------------------------------------------------------------

def test_segmentar_mprr_964_captura_3_familias():
    materias = segmentar_materias(
        _fixture("mprr_2026-05-20-964.md"), "MPRR", "https://x/964.pdf"
    )
    cont = _contagem(materias)
    assert cont.get("PORTARIA", 0) >= 15
    assert cont.get("EXTRATO", 0) >= 4
    assert cont.get("AVISO", 0) >= 1


def test_segmentar_mprr_2022_captura_extratos_de_gasto():
    # Edição antiga: formato "PORTARIA Nº" (sem hífen antes do Nº) + extratos
    # de gasto (NOTA DE EMPENHO, TERMO ADITIVO AO CONTRATO) + AVISO licitação.
    materias = segmentar_materias(
        _fixture("mprr_2022-04-19.md"), "MPRR", "https://x/2022.pdf"
    )
    cont = _contagem(materias)
    assert cont.get("PORTARIA", 0) >= 25
    assert cont.get("EXTRATO", 0) >= 10
    assert cont.get("AVISO", 0) >= 1


def test_segmentar_mprr_939_captura_portarias_pgj_e_dg():
    # Edição dominada por portarias (PGJ, DG, DA) — formato "PORTARIA - Nº".
    materias = segmentar_materias(
        _fixture("mprr_2026-04-10-939.md"), "MPRR", "https://x/939.pdf"
    )
    cont = _contagem(materias)
    assert cont.get("PORTARIA", 0) >= 12


def test_segmentar_mprr_so_produz_tipos_das_3_familias():
    materias = segmentar_materias(
        _fixture("mprr_2026-05-20-964.md"), "MPRR", "https://x/964.pdf"
    )
    assert materias
    assert {m.tipo for m in materias} <= {"PORTARIA", "EXTRATO", "AVISO"}


def test_segmentar_mprr_nao_captura_ruido():
    """Ruído (R E S O L V E, assinaturas, fragmentos de corpo em negrito)
    não vira matéria: toda matéria começa por um cabeçalho de família."""
    materias = segmentar_materias(
        _fixture("mprr_2026-05-20-964.md"), "MPRR", "https://x/964.pdf"
    )
    for m in materias:
        cabecalho = m.texto.lstrip("*# ").upper()
        assert cabecalho.startswith(("PORTARIA", "EXTRATO", "AVISO")), m.texto[:60]


# ---------------------------------------------------------------------------
# GRUPO C — segmentar_materias (TJRR) — inalterado (layout textual funciona)
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
# GRUPO E — Múltiplas matérias e isolamento (sobre fixture real)
# ---------------------------------------------------------------------------

def test_segmentar_mprr_multiplas_familias_no_real_964():
    materias = segmentar_materias(
        _fixture("mprr_2026-05-20-964.md"), "MPRR", "https://x/964.pdf"
    )
    tipos = {m.tipo for m in materias}
    assert "PORTARIA" in tipos
    assert "EXTRATO" in tipos


def test_segmentar_materias_isoladas_nao_vazam_texto():
    """Cada matéria contém exatamente UM cabeçalho de família — o seu.

    Falha se o fatiamento por posição vazar (matéria englobando o cabeçalho
    da próxima) ou se a implementação retornar o Markdown inteiro N vezes.
    """
    materias = segmentar_materias(
        _fixture("mprr_2026-05-20-964.md"), "MPRR", "https://x/964.pdf"
    )
    cabecalho = re.compile(r"(?m)^\*\*\s*(?:PORTARIA|EXTRATO|AVISO)\b")
    for i, m in enumerate(materias):
        n = len(cabecalho.findall(m.texto))
        assert n == 1, f"matéria {i} ({m.tipo}) tem {n} cabeçalhos no texto"


# ---------------------------------------------------------------------------
# GRUPO H — Campos de classificação opcionais (Sub-ciclo 8.6a)
# ---------------------------------------------------------------------------

def test_materia_defaults_dos_campos_de_classificacao():
    m = Materia(orgao="MPRR", tipo="PORTARIA", texto="x", pdf_url="y")
    assert m.categoria is None
    assert m.manchete is None
    assert m.resumo is None
    assert m.valor_rs is None
    assert m.tags == []
    assert m.relevante is False


def test_materia_aceita_campos_de_classificacao_completos():
    m = Materia(
        orgao="MPRR",
        tipo="EXTRATO",
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
    m1 = Materia(orgao="MPRR", tipo="PORTARIA", texto="x", pdf_url="y")
    m2 = Materia(orgao="MPRR", tipo="PORTARIA", texto="x", pdf_url="y")

    m1.tags.append("frota")

    assert m1.tags == ["frota"]
    assert m2.tags == []


def test_materia_classificada_compativel_com_segmentar_materias():
    """Backward compat: segmentar_materias produz Materia com defaults
    seguros nos campos de classificação (preenchidos depois no 8.6c)."""
    materias = segmentar_materias(MD_MPRR_PORTARIA_PGJ, "MPRR", "https://x.pdf")
    assert len(materias) >= 1
    m = materias[0]
    assert m.categoria is None
    assert m.manchete is None
    assert m.resumo is None
    assert m.valor_rs is None
    assert m.tags == []
    assert m.relevante is False
