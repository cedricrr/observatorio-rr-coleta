"""Testes do parser HTML → sidecar dict (Ciclo 11.5)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.sidecar_backfill import parse_jornal_para_sidecar

_FIXTURE = Path(__file__).parent / "fixtures" / "jornal_sample.html"


@pytest.fixture
def html_sample() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def sidecar_sample(html_sample) -> dict:
    return parse_jornal_para_sidecar(
        html_sample,
        data_edicao=date(2026, 5, 15),
        url_jornal="https://pub.r2.dev/jornal/2026-05-15.html",
    )


def test_cabecalho_preenchido(sidecar_sample):
    assert sidecar_sample["versao"] == 1
    assert sidecar_sample["data_edicao"] == "2026-05-15"
    assert sidecar_sample["data_formatada"] == "15 de maio de 2026"
    assert sidecar_sample["url_jornal"] == (
        "https://pub.r2.dev/jornal/2026-05-15.html"
    )


def test_total_relevantes_bate_com_qtd_de_materias(sidecar_sample):
    assert sidecar_sample["total_relevantes"] == 3
    assert len(sidecar_sample["materias"]) == 3


def test_extrai_orgao_por_section(sidecar_sample):
    orgaos = [m["orgao"] for m in sidecar_sample["materias"]]
    assert orgaos == ["MPRR", "MPRR", "TJRR"]


def test_extrai_manchete_de_h3(sidecar_sample):
    manchetes = [m["manchete"] for m in sidecar_sample["materias"]]
    assert manchetes[0] == "MPRR contrata fornecedor de TI por R$ 152.340,50"
    assert manchetes[1] == "Portaria PGJ designa promotor para força-tarefa"
    assert manchetes[2] == "TJRR institui Câmara de Conciliação"


def test_extrai_resumo_de_p_resumo(sidecar_sample):
    primeiro = sidecar_sample["materias"][0]
    assert "Resumo curto" in primeiro["resumo"]
    assert "ção, áéíóú" in primeiro["resumo"]


def test_extrai_categoria_do_span_categoria(sidecar_sample):
    cats = [m["categoria"] for m in sidecar_sample["materias"]]
    assert cats == [
        "Contratação", "Designação", "Estrutura administrativa",
    ]


def test_extrai_tags_filtrando_categoria(sidecar_sample):
    # tags não devem incluir o span da categoria
    tags = [m["tags"] for m in sidecar_sample["materias"]]
    assert tags[0] == ["licitação", "TI"]
    assert tags[1] == ["PGJ", "força-tarefa"]
    assert tags[2] == ["conciliação"]


def test_parseia_valor_rs_brasileiro(sidecar_sample):
    valores = [m["valor_rs"] for m in sidecar_sample["materias"]]
    assert valores[0] == 152340.50
    # Sem span.valor → None
    assert valores[1] is None
    assert valores[2] is None


def test_extrai_pdf_url_da_fonte(sidecar_sample):
    urls = [m["pdf_url"] for m in sidecar_sample["materias"]]
    assert urls[0] == "https://pub.r2.dev/mprr/2026/05/15-961.pdf"
    assert urls[1] == "https://pub.r2.dev/mprr/2026/05/15-961.pdf"
    assert urls[2] == "https://pub.r2.dev/tjrr/2026/05/15.pdf"


def test_pagina_e_none_porque_nao_existe_no_html(sidecar_sample):
    for m in sidecar_sample["materias"]:
        assert m["pagina"] is None


def test_tipo_default_quando_nao_recuperavel(sidecar_sample):
    # tipo não é exposto no HTML — parser preenche com string padrão.
    for m in sidecar_sample["materias"]:
        assert m["tipo"] == "DESCONHECIDO"


def test_idempotente(html_sample):
    """Parsear duas vezes produz dict idêntico (sem efeitos colaterais)."""
    a = parse_jornal_para_sidecar(
        html_sample, date(2026, 5, 15), "https://x/y.html",
    )
    b = parse_jornal_para_sidecar(
        html_sample, date(2026, 5, 15), "https://x/y.html",
    )
    assert a == b


def test_empty_state_html_devolve_materias_vazias():
    html_vazio = """
    <html><body><div class="container">
        <header class="jornal-cabecalho"><h1>x</h1></header>
        <div class="empty-state">Nenhuma matéria com relevância editorial nesta edição.</div>
    </div></body></html>
    """
    s = parse_jornal_para_sidecar(
        html_vazio, date(2026, 5, 15), "https://x/y.html",
    )
    assert s["total_relevantes"] == 0
    assert s["materias"] == []
