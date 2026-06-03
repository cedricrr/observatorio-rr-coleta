"""Testes do helper de sidecar JSON (Ciclos 11.1, 11.2)."""

from __future__ import annotations

from datetime import date

from scripts.segmentar import Materia
from scripts.sidecar import (
    SCHEMA_VERSAO,
    materia_para_dict_sidecar,
    montar_sidecar,
)


def _materia_classificada(**overrides) -> Materia:
    """Constrói uma Materia preenchida pelo classificador (todos campos ok)."""
    defaults = dict(
        orgao="MPRR",
        tipo="EXTRATO",
        texto="**EXTRATO DE CONTRATO**\nNº 123/2026 ...",
        pdf_url="https://pub.r2.dev/mprr/2026/05/15-967.pdf",
        pagina=3,
        categoria="Contratação",
        manchete="MPRR contrata fornecedor X por R$ 152.340,50",
        resumo="Resumo de 1-2 frases sobre a contratação.",
        valor_rs=152340.50,
        tags=["licitação", "TI"],
        relevante=True,
    )
    defaults.update(overrides)
    return Materia(**defaults)


def test_schema_versao_exposta():
    assert SCHEMA_VERSAO == 1


def test_dict_contem_apenas_chaves_do_schema():
    m = _materia_classificada()
    d = materia_para_dict_sidecar(m)
    esperadas = {
        "orgao", "tipo", "categoria", "manchete", "resumo",
        "valor_rs", "tags", "pdf_url", "pagina",
    }
    assert set(d.keys()) == esperadas


def test_dict_nao_contem_texto_markdown_bruto():
    m = _materia_classificada()
    d = materia_para_dict_sidecar(m)
    assert "texto" not in d


def test_dict_nao_contem_flag_relevante():
    # Apenas relevantes vão pro sidecar; flag é redundante.
    m = _materia_classificada()
    d = materia_para_dict_sidecar(m)
    assert "relevante" not in d


def test_dict_preserva_valores_corretos():
    m = _materia_classificada(valor_rs=987654.32, tags=["a", "b", "c"])
    d = materia_para_dict_sidecar(m)
    assert d["orgao"] == "MPRR"
    assert d["tipo"] == "EXTRATO"
    assert d["categoria"] == "Contratação"
    assert d["manchete"] == "MPRR contrata fornecedor X por R$ 152.340,50"
    assert d["resumo"] == "Resumo de 1-2 frases sobre a contratação."
    assert d["valor_rs"] == 987654.32
    assert d["tags"] == ["a", "b", "c"]
    assert d["pdf_url"] == "https://pub.r2.dev/mprr/2026/05/15-967.pdf"
    assert d["pagina"] == 3


def test_valor_rs_none_vira_none_nao_some():
    m = _materia_classificada(valor_rs=None)
    d = materia_para_dict_sidecar(m)
    assert "valor_rs" in d
    assert d["valor_rs"] is None


def test_pagina_none_vira_none_nao_some():
    m = _materia_classificada(pagina=None)
    d = materia_para_dict_sidecar(m)
    assert "pagina" in d
    assert d["pagina"] is None


def test_tags_vazias_permanecem_lista():
    m = _materia_classificada(tags=[])
    d = materia_para_dict_sidecar(m)
    assert d["tags"] == []
    assert isinstance(d["tags"], list)


# ---------------------------------------------------------------------------
# Ciclo 11.2 — montar_sidecar (cabeçalho + filtro)
# ---------------------------------------------------------------------------


def test_montar_sidecar_inclui_metadados_cabecalho():
    materias = [_materia_classificada()]
    s = montar_sidecar(
        materias,
        data_edicao=date(2026, 5, 15),
        url_jornal="https://pub.r2.dev/jornal/2026-05-15.html",
    )
    assert s["versao"] == 1
    assert s["data_edicao"] == "2026-05-15"
    assert s["data_formatada"] == "15 de maio de 2026"
    assert s["url_jornal"] == "https://pub.r2.dev/jornal/2026-05-15.html"
    assert s["total_relevantes"] == 1


def test_montar_sidecar_filtra_irrelevantes():
    relevante = _materia_classificada(manchete="REL", relevante=True)
    descartada = _materia_classificada(manchete="DESC", relevante=False)
    s = montar_sidecar(
        [relevante, descartada],
        data_edicao=date(2026, 5, 15),
        url_jornal="https://x/y.html",
    )
    assert s["total_relevantes"] == 1
    assert len(s["materias"]) == 1
    assert s["materias"][0]["manchete"] == "REL"


def test_montar_sidecar_preserva_ordem_das_materias():
    a = _materia_classificada(manchete="A")
    b = _materia_classificada(manchete="B")
    c = _materia_classificada(manchete="C")
    s = montar_sidecar(
        [a, b, c],
        data_edicao=date(2026, 5, 15),
        url_jornal="https://x/y.html",
    )
    assert [m["manchete"] for m in s["materias"]] == ["A", "B", "C"]


def test_montar_sidecar_materias_sao_dicts_do_schema():
    m = _materia_classificada()
    s = montar_sidecar(
        [m], data_edicao=date(2026, 5, 15), url_jornal="https://x/y.html",
    )
    # Cada item da lista deve passar pelo helper individual
    assert s["materias"][0] == materia_para_dict_sidecar(m)


def test_montar_sidecar_lista_vazia_quando_nada_relevante():
    a = _materia_classificada(relevante=False)
    s = montar_sidecar(
        [a], data_edicao=date(2026, 5, 15), url_jornal="https://x/y.html",
    )
    assert s["total_relevantes"] == 0
    assert s["materias"] == []


def test_montar_sidecar_aceita_lista_vazia():
    s = montar_sidecar(
        [], data_edicao=date(2026, 5, 15), url_jornal="https://x/y.html",
    )
    assert s["total_relevantes"] == 0
    assert s["materias"] == []
    assert s["data_formatada"] == "15 de maio de 2026"
