"""Testes do renderizador de jornal HTML editorial (Ciclo 8.7)."""

from datetime import date

from scripts.renderizar import renderizar_jornal
from scripts.segmentar import Materia


def _materia_classificada(
    orgao: str = "MPRR",
    tipo: str = "EXTRATO_CONTRATO",
    categoria: str = "Contratos e licitações",
    manchete: str = "MPRR contrata serviço por R$ 100 mil",
    resumo: str = "O Ministério Público formalizou contrato.",
    valor_rs: float | None = 100000.00,
    tags: list[str] | None = None,
    relevante: bool = True,
) -> Materia:
    return Materia(
        orgao=orgao,
        tipo=tipo,
        texto="conteúdo bruto da matéria",
        pdf_url="https://example.com/x.pdf",
        categoria=categoria,
        manchete=manchete,
        resumo=resumo,
        valor_rs=valor_rs,
        tags=tags if tags is not None else ["test"],
        relevante=relevante,
    )


# =============================================================
# GRUPO A — Estrutura básica do HTML
# =============================================================


def test_renderiza_retorna_string_html():
    materias = [_materia_classificada()]
    html = renderizar_jornal(materias, date(2026, 4, 30))
    assert isinstance(html, str)
    assert len(html) > 100
    assert "<html" in html.lower()
    assert "</html>" in html.lower()
    assert "<head>" in html.lower()
    assert "<body>" in html.lower()


def test_renderiza_inclui_css_embedded():
    materias = [_materia_classificada()]
    html = renderizar_jornal(materias, date(2026, 4, 30))
    assert "<style>" in html.lower()
    inicio_style = html.lower().find("<style>")
    fim_head = html.lower().find("</head>")
    assert 0 < inicio_style < fim_head


def test_renderiza_inclui_google_fonts():
    materias = [_materia_classificada()]
    html = renderizar_jornal(materias, date(2026, 4, 30))
    assert "Fraunces" in html
    assert "Inter" in html
    assert "JetBrains" in html
    assert "fonts.googleapis.com" in html


# =============================================================
# GRUPO B — Conteúdo das matérias
# =============================================================


def test_renderiza_inclui_manchete():
    manchete_unica = "MANCHETE_UNICA_XYZ_RASTREAVEL"
    mat = _materia_classificada(manchete=manchete_unica)
    html = renderizar_jornal([mat], date(2026, 4, 30))
    assert manchete_unica in html


def test_renderiza_inclui_resumo():
    resumo_unico = "Resumo único rastreável da matéria."
    mat = _materia_classificada(resumo=resumo_unico)
    html = renderizar_jornal([mat], date(2026, 4, 30))
    assert resumo_unico in html


def test_renderiza_inclui_categoria():
    mat = _materia_classificada(categoria="Investigações e inquéritos")
    html = renderizar_jornal([mat], date(2026, 4, 30))
    assert "Investigações e inquéritos" in html


def test_renderiza_formata_valor_rs_pt_br():
    mat = _materia_classificada(valor_rs=183268.52)
    html = renderizar_jornal([mat], date(2026, 4, 30))
    assert "183.268,52" in html or "183 268,52" in html


def test_renderiza_sem_valor_rs_quando_none():
    mat = _materia_classificada(valor_rs=None, manchete="Sem valor")
    html = renderizar_jornal([mat], date(2026, 4, 30))
    assert "Sem valor" in html
    assert "R$ None" not in html


# =============================================================
# GRUPO C — Filtro de relevância
# =============================================================


def test_renderiza_omite_materias_nao_relevantes():
    relevante = _materia_classificada(
        manchete="DEVE_APARECER_NO_HTML", relevante=True,
    )
    irrelevante = _materia_classificada(
        manchete="NAO_DEVE_APARECER_NO_HTML", relevante=False,
    )
    html = renderizar_jornal([relevante, irrelevante], date(2026, 4, 30))
    assert "DEVE_APARECER_NO_HTML" in html
    assert "NAO_DEVE_APARECER_NO_HTML" not in html


def test_renderiza_lista_vazia_de_relevantes():
    mats = [
        _materia_classificada(relevante=False, manchete="X"),
        _materia_classificada(relevante=False, manchete="Y"),
    ]
    html = renderizar_jornal(mats, date(2026, 4, 30))
    assert isinstance(html, str)
    assert "<html" in html.lower()
    assert "<<<MANCHETE_X>>>" not in html


# =============================================================
# GRUPO D — Agrupamento por órgão
# =============================================================


def test_renderiza_mprr_aparece_antes_de_tjrr():
    mat_tjrr = _materia_classificada(
        orgao="TJRR", manchete="MATERIA_TJRR_UNICA",
    )
    mat_mprr = _materia_classificada(
        orgao="MPRR", manchete="MATERIA_MPRR_UNICA",
    )
    html = renderizar_jornal([mat_tjrr, mat_mprr], date(2026, 4, 30))
    pos_mprr = html.find("MATERIA_MPRR_UNICA")
    pos_tjrr = html.find("MATERIA_TJRR_UNICA")
    assert pos_mprr > 0
    assert pos_tjrr > 0
    assert pos_mprr < pos_tjrr


def test_renderiza_secao_por_orgao():
    mats = [
        _materia_classificada(orgao="MPRR", manchete="M1"),
        _materia_classificada(orgao="TJRR", manchete="T1"),
    ]
    html = renderizar_jornal(mats, date(2026, 4, 30))
    assert "MPRR" in html
    assert "TJRR" in html


# =============================================================
# GRUPO E — Metadados ricos
# =============================================================


def test_renderiza_data_em_portugues():
    html = renderizar_jornal(
        [_materia_classificada()],
        date(2026, 4, 30),
    )
    assert "30" in html
    assert "abril" in html.lower() or "04" in html
    assert "2026" in html


def test_renderiza_inclui_num_edicao_quando_fornecido():
    html = renderizar_jornal(
        [_materia_classificada()],
        date(2026, 4, 30),
        num_edicao=951,
    )
    assert "951" in html


def test_renderiza_omite_num_edicao_quando_none():
    html = renderizar_jornal(
        [_materia_classificada()],
        date(2026, 4, 30),
        num_edicao=None,
    )
    assert "None" not in html
    assert "edição n/a" not in html.lower()


def test_renderiza_total_de_materias():
    mats = [
        _materia_classificada(manchete=f"Materia {i}")
        for i in range(5)
    ]
    html = renderizar_jornal(mats, date(2026, 4, 30))
    assert "5" in html


# =============================================================
# GRUPO F — Edge cases
# =============================================================


def test_renderiza_lista_completamente_vazia():
    html = renderizar_jornal([], date(2026, 4, 30))
    assert isinstance(html, str)
    assert "<html" in html.lower()
    assert "</html>" in html.lower()


def test_renderiza_escapa_html_em_manchete():
    mat = _materia_classificada(
        manchete="Empresa <script>alert(1)</script> contratada",
    )
    html = renderizar_jornal([mat], date(2026, 4, 30))
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html or "alert" in html
