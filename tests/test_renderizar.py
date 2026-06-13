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


# =============================================================
# GRUPO G — Link para a fonte primária (PDF do diário)
# =============================================================


def test_renderiza_inclui_link_para_pdf_original():
    """Cada matéria deve linkar para o PDF original (fonte primária).

    O leitor precisa poder verificar a manchete contra o documento
    oficial. Sem link, o jornal vira síntese editorial sem verificável.
    """
    pdf_url_unica = "https://files.pub.dev/test/2026-04-30-fonte-rastreavel.pdf"
    mat = _materia_classificada()
    mat.pdf_url = pdf_url_unica
    html = renderizar_jornal([mat], date(2026, 4, 30))
    assert (
        f'href="{pdf_url_unica}"' in html
        or f"href='{pdf_url_unica}'" in html
    )
    assert "Fonte" in html


# =============================================================
# GRUPO H — formatar_data (ISO → PT-BR abreviado) — índice
# =============================================================
#
# Helper consumido como global Jinja `formatar_data` no índice da home,
# para substituir a data ISO crua ("2026-06-08") por "08 JUN 2026".


def test_formatar_data_abrev_converte_iso_para_pt_br():
    from scripts.renderizar import _formatar_data_abrev
    assert _formatar_data_abrev("2026-06-08") == "08 JUN 2026"


def test_formatar_data_abrev_dia_com_dois_digitos():
    from scripts.renderizar import _formatar_data_abrev
    # dia de um dígito ganha zero à esquerda
    assert _formatar_data_abrev("2026-01-03") == "03 JAN 2026"


def test_formatar_data_abrev_string_vazia_retorna_vazio():
    from scripts.renderizar import _formatar_data_abrev
    assert _formatar_data_abrev("") == ""


def test_formatar_data_abrev_none_retorna_vazio():
    from scripts.renderizar import _formatar_data_abrev
    assert _formatar_data_abrev(None) == ""


def test_formatar_data_abrev_todos_os_doze_meses():
    from scripts.renderizar import _formatar_data_abrev
    esperado = [
        "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
        "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
    ]
    for mes in range(1, 13):
        iso = date(2026, mes, 1).isoformat()
        assert _formatar_data_abrev(iso) == f"01 {esperado[mes - 1]} 2026"


# =============================================================
# GRUPO I — ilustração SVG temática por categoria (coluna do hero)
# =============================================================
#
# Helper consumido como global Jinja `ilustracao_categoria` no índice:
# devolve um SVG inline escolhido pela categoria do hero, com cor de
# acento por órgão (MPRR/TJRR).


def test_ilustracao_categoria_retorna_svg():
    from scripts.renderizar import _ilustracao_categoria
    svg = str(_ilustracao_categoria("Investigações e inquéritos", "MPRR"))
    assert svg.startswith("<svg")
    assert "</svg>" in svg


def test_ilustracao_categoria_acento_muda_por_orgao():
    from scripts.renderizar import _ilustracao_categoria
    mprr = str(_ilustracao_categoria("Contratos e licitações", "MPRR"))
    tjrr = str(_ilustracao_categoria("Contratos e licitações", "TJRR"))
    assert "#c8102e" in mprr   # vermelho MPRR
    assert "#1d4e89" in tjrr   # azul TJRR
    assert mprr != tjrr


def test_ilustracao_categoria_desconhecida_usa_fallback():
    from scripts.renderizar import _ilustracao_categoria
    svg = str(_ilustracao_categoria("Categoria Inexistente", "MPRR"))
    assert svg.startswith("<svg")


def test_ilustracao_categoria_none_nao_quebra():
    from scripts.renderizar import _ilustracao_categoria
    svg = str(_ilustracao_categoria(None, None))
    assert svg.startswith("<svg")


def test_ilustracao_categoria_cobre_todas_as_categorias_validas():
    import xml.etree.ElementTree as ET

    from scripts.classificar import CATEGORIAS_VALIDAS
    from scripts.renderizar import _ilustracao_categoria
    vistos = set()
    for cat in CATEGORIAS_VALIDAS:
        svg = str(_ilustracao_categoria(cat, "MPRR"))
        ET.fromstring(svg)   # XML bem-formado
        vistos.add(svg)
    # categorias específicas geram ilustrações distintas ("Outros" = fallback)
    assert len(vistos) >= 8


# =============================================================
# Metadados de publicação: description, canonical, OG (Ciclo 12)
# =============================================================


def test_renderiza_tem_meta_description_dinamica():
    mats = [_materia_classificada(), _materia_classificada(relevante=False)]
    html = renderizar_jornal(mats, date(2026, 4, 30))
    assert (
        '<meta name="description" content="Edição de 30 de abril de 2026 — '
        "1 matéria relevante dos diários oficiais de Roraima.\"" in html
    )


def test_renderiza_meta_description_pluraliza():
    mats = [_materia_classificada(), _materia_classificada()]
    html = renderizar_jornal(mats, date(2026, 4, 30))
    assert "2 matérias relevantes" in html


def test_renderiza_com_url_canonica_tem_canonical_e_og():
    html = renderizar_jornal(
        [_materia_classificada()],
        date(2026, 4, 30),
        url_canonica="https://pub-xxx.r2.dev/jornal/2026-04-30.html",
    )
    assert (
        '<link rel="canonical" href="https://pub-xxx.r2.dev/jornal/2026-04-30.html">'
        in html
    )
    assert (
        '<meta property="og:url" content="https://pub-xxx.r2.dev/jornal/2026-04-30.html">'
        in html
    )
    assert (
        '<meta property="og:title" content="Observatório Roraima — 30 de abril de 2026">'
        in html
    )
    assert '<meta property="og:type" content="article">' in html
    assert '<meta name="twitter:card" content="summary">' in html


def test_renderiza_sem_url_canonica_nao_tem_canonical():
    html = renderizar_jornal([_materia_classificada()], date(2026, 4, 30))
    assert 'rel="canonical"' not in html
    assert 'property="og:' not in html


def test_renderiza_tem_favicon_inline():
    html = renderizar_jornal([_materia_classificada()], date(2026, 4, 30))
    assert '<link rel="icon" href="data:image/svg+xml,' in html


# =============================================================
# Cloudflare Web Analytics (Ciclo 12) — beacon condicional via env
# =============================================================


def test_renderiza_com_token_emite_beacon_analytics(monkeypatch):
    monkeypatch.setenv("CF_ANALYTICS_TOKEN", "tok-abc123")
    html = renderizar_jornal([_materia_classificada()], date(2026, 4, 30))
    assert "static.cloudflareinsights.com/beacon.min.js" in html
    assert "tok-abc123" in html


def test_renderiza_sem_token_nao_emite_beacon(monkeypatch):
    monkeypatch.delenv("CF_ANALYTICS_TOKEN", raising=False)
    html = renderizar_jornal([_materia_classificada()], date(2026, 4, 30))
    assert "cloudflareinsights" not in html


def test_renderiza_tem_skip_link_e_main_conteudo():
    """Acessibilidade: skip-link no topo + <main id="conteudo"> (padrão da home)."""
    html = renderizar_jornal([_materia_classificada()], date(2026, 4, 30))
    assert '<a class="skip-link" href="#conteudo">' in html
    assert 'id="conteudo"' in html


# =============================================================
# GRUPO Sessão 13.3 — ganchos para o acervo na notícia
# =============================================================


def test_tags_viram_links_de_busca_com_url_busca():
    materia = _materia_classificada(tags=["Empresa XYZ Ltda"])
    html = renderizar_jornal([materia], date(2026, 5, 15), url_busca="busca.html")
    assert 'href="busca.html?q=Empresa%20XYZ%20Ltda"' in html


def test_tags_continuam_spans_sem_url_busca():
    materia = _materia_classificada(tags=["Empresa XYZ Ltda"])
    html = renderizar_jornal([materia], date(2026, 5, 15))
    assert "busca.html?q=" not in html
    assert "Empresa XYZ Ltda" in html


def test_bloco_acervo_presente_com_contagem():
    materia = _materia_classificada(tags=["Empresa XYZ Ltda"])
    html = renderizar_jornal(
        [materia],
        date(2026, 5, 15),
        url_busca="busca.html",
        ocorrencias_acervo={"Empresa XYZ Ltda": 12},
    )
    assert "Este assunto no acervo" in html
    assert "12" in html


def test_bloco_acervo_omitido_sem_contagem():
    # falha do Solr no build → ocorrencias_acervo vazio → bloco omitido
    materia = _materia_classificada(tags=["Empresa XYZ Ltda"])
    html = renderizar_jornal(
        [materia], date(2026, 5, 15), url_busca="busca.html",
        ocorrencias_acervo={},
    )
    assert "Este assunto no acervo" not in html


def test_bloco_conversao_varia_por_categoria():
    contrato = _materia_classificada(categoria="Contratos e licitações")
    concurso = _materia_classificada(
        categoria="Concursos e delegações", valor_rs=None,
        manchete="Convocados aprovados do concurso",
    )
    outro = _materia_classificada(
        categoria="Atos normativos", valor_rs=None,
        manchete="Nova resolução administrativa",
    )

    html_contrato = renderizar_jornal([contrato], date(2026, 5, 15), url_busca="busca.html")
    html_concurso = renderizar_jornal([concurso], date(2026, 5, 15), url_busca="busca.html")
    html_outro = renderizar_jornal([outro], date(2026, 5, 15), url_busca="busca.html")

    assert "empresa" in html_contrato.split("cta-busca")[1][:300]
    assert "seu nome" in html_concurso.split("cta-busca")[1][:300]
    assert "OAB" in html_outro.split("cta-busca")[1][:300]


def test_bloco_conversao_ausente_sem_url_busca():
    materia = _materia_classificada()
    html = renderizar_jornal([materia], date(2026, 5, 15))
    assert "cta-busca" not in html
