"""Testes do publicador de jornal/índice no R2 (Ciclo 9.4)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.publicar import (
    agregar_destaques_recentes,
    baixar_sidecar,
    coletar_datas_publicaveis,
    gerar_indice,
    publicar_indice,
    publicar_jornal,
    publicar_sidecar,
    publicar_tudo,
)


@pytest.fixture
def mock_r2():
    """R2Client mock — upload retorna URL pública canônica."""
    r2 = MagicMock()

    def _upload_side_effect(caminho, chave, *args, **kwargs):
        return f"https://pub-xxx.r2.dev/{chave}"

    r2.upload.side_effect = _upload_side_effect
    return r2


def _criar_jsons(tmp_path: Path, datas_por_fonte: dict[str, list[str]]) -> Path:
    """Helper: cria data/diarios/{fonte}/{data}.json com conteúdo mínimo.

    datas_por_fonte: e.g. {"mprr": ["2026-05-15-961", "2026-05-14-960"], "tjrr": ["2026-05-15"]}
    """
    for fonte, nomes in datas_por_fonte.items():
        (tmp_path / fonte).mkdir(parents=True, exist_ok=True)
        for nome in nomes:
            (tmp_path / fonte / f"{nome}.json").write_text(
                '{"orgao":"' + fonte + '","data_edicao":"x"}'
            )
    return tmp_path


def _criar_html_falso(tmp_path: Path, nome: str = "2026-05-15.html") -> Path:
    arquivo = tmp_path / nome
    arquivo.write_text("<html><body>fake</body></html>")
    return arquivo


# =============================================================
# publicar_jornal
# =============================================================


def test_publicar_jornal_chama_upload_com_content_type_html(mock_r2, tmp_path):
    html_path = _criar_html_falso(tmp_path)
    publicar_jornal(html_path, mock_r2, date(2026, 5, 15))
    kwargs = mock_r2.upload.call_args.kwargs
    assert kwargs["content_type"] == "text/html; charset=utf-8"


def test_publicar_jornal_chave_segue_padrao_aaaa_mm_dd(mock_r2, tmp_path):
    html_path = _criar_html_falso(tmp_path)
    publicar_jornal(html_path, mock_r2, date(2026, 5, 15))
    args = mock_r2.upload.call_args.args
    assert args[1] == "jornal/2026-05-15.html"


def test_publicar_jornal_retorna_url_publica(mock_r2, tmp_path):
    html_path = _criar_html_falso(tmp_path)
    url = publicar_jornal(html_path, mock_r2, date(2026, 5, 15))
    assert url == "https://pub-xxx.r2.dev/jornal/2026-05-15.html"


def test_publicar_jornal_inclui_metadado_data_edicao(mock_r2, tmp_path):
    html_path = _criar_html_falso(tmp_path)
    publicar_jornal(html_path, mock_r2, date(2026, 5, 15))
    kwargs = mock_r2.upload.call_args.kwargs
    assert kwargs["metadados"] == {"data-edicao": "2026-05-15"}


# =============================================================
# coletar_datas_publicaveis
# =============================================================


def test_coletar_datas_publicaveis_agrupa_mprr_e_tjrr_por_data(tmp_path):
    _criar_jsons(
        tmp_path,
        {
            "mprr": ["2026-05-15-961", "2026-05-14-960"],
            "tjrr": ["2026-05-15", "2026-05-13"],
        },
    )
    datas = coletar_datas_publicaveis(tmp_path)
    assert date(2026, 5, 15) in datas
    assert date(2026, 5, 14) in datas
    assert date(2026, 5, 13) in datas
    assert len(datas) == 3


def test_coletar_datas_publicaveis_ordena_descendente(tmp_path):
    _criar_jsons(
        tmp_path,
        {
            "mprr": ["2026-05-11-957", "2026-05-15-961", "2026-05-13-959"],
        },
    )
    datas = coletar_datas_publicaveis(tmp_path)
    assert datas == [date(2026, 5, 15), date(2026, 5, 13), date(2026, 5, 11)]


def test_coletar_datas_publicaveis_parseia_sufixo_numero_edicao(tmp_path):
    _criar_jsons(tmp_path, {"mprr": ["2022-04-26-4"]})
    datas = coletar_datas_publicaveis(tmp_path)
    assert datas == [date(2022, 4, 26)]


def test_coletar_datas_publicaveis_dir_vazio_retorna_lista_vazia(tmp_path):
    datas = coletar_datas_publicaveis(tmp_path)
    assert datas == []


# =============================================================
# gerar_indice
# =============================================================


def test_gerar_indice_html_contem_links_para_cada_data(tmp_path):
    _criar_jsons(
        tmp_path,
        {"mprr": ["2026-05-15-961", "2026-05-14-960"]},
    )
    html = gerar_indice(tmp_path, public_domain="pub-xxx.r2.dev")
    assert 'href="https://pub-xxx.r2.dev/jornal/2026-05-15.html"' in html
    assert 'href="https://pub-xxx.r2.dev/jornal/2026-05-14.html"' in html


def test_gerar_indice_html_tem_estrutura_basica(tmp_path):
    _criar_jsons(tmp_path, {"mprr": ["2026-05-15-961"]})
    html = gerar_indice(tmp_path, public_domain="pub-xxx.r2.dev")
    assert "<html" in html.lower()
    assert "<head" in html.lower()
    assert "<body" in html.lower()
    assert "</html>" in html.lower()


def test_gerar_indice_empty_state_quando_zero_edicoes(tmp_path):
    html = gerar_indice(tmp_path, public_domain="pub-xxx.r2.dev")
    assert "<html" in html.lower()
    assert "0" in html or "Nenhuma" in html or "Sem edições" in html


# =============================================================
# publicar_indice
# =============================================================


def test_publicar_indice_sobe_em_jornal_index_html(mock_r2):
    html_indice = "<html><body>indice fake</body></html>"
    publicar_indice(html_indice, mock_r2)
    args = mock_r2.upload.call_args.args
    kwargs = mock_r2.upload.call_args.kwargs
    assert args[1] == "jornal/index.html"
    assert kwargs["content_type"] == "text/html; charset=utf-8"


def test_publicar_indice_passa_cache_control_curto(mock_r2):
    """Ciclo 10.2: índice sobe com max-age curto p/ evitar índice stale no CDN."""
    publicar_indice("<html></html>", mock_r2)
    kwargs = mock_r2.upload.call_args.kwargs
    assert kwargs["cache_control"] == "public, max-age=300"


# =============================================================
# publicar_sidecar (Ciclo 11.3)
# =============================================================


def _upload_capturando_bytes(capturados: dict):
    """Side effect que captura os bytes do arquivo enviado e devolve URL canônica."""

    def _side_effect(caminho, chave, *args, **kwargs):
        capturados["bytes"] = caminho.read_bytes()
        capturados["chave"] = chave
        capturados["kwargs"] = kwargs
        return f"https://pub-xxx.r2.dev/{chave}"

    return _side_effect


def test_publicar_sidecar_chave_segue_padrao_json(mock_r2):
    publicar_sidecar({"versao": 1, "materias": []}, mock_r2, date(2026, 5, 15))
    args = mock_r2.upload.call_args.args
    assert args[1] == "jornal/2026-05-15.json"


def test_publicar_sidecar_content_type_application_json(mock_r2):
    publicar_sidecar({"versao": 1, "materias": []}, mock_r2, date(2026, 5, 15))
    kwargs = mock_r2.upload.call_args.kwargs
    assert kwargs["content_type"] == "application/json"


def test_publicar_sidecar_retorna_url_publica(mock_r2):
    url = publicar_sidecar(
        {"versao": 1, "materias": []}, mock_r2, date(2026, 5, 15),
    )
    assert url == "https://pub-xxx.r2.dev/jornal/2026-05-15.json"


def test_publicar_sidecar_inclui_metadado_data_edicao(mock_r2):
    publicar_sidecar({"versao": 1, "materias": []}, mock_r2, date(2026, 5, 15))
    kwargs = mock_r2.upload.call_args.kwargs
    assert kwargs["metadados"] == {"data-edicao": "2026-05-15"}


def test_publicar_sidecar_sem_cache_control(mock_r2):
    # Sidecar é imutável (idem HTML do jornal); CDN cache padrão é OK.
    publicar_sidecar({"versao": 1, "materias": []}, mock_r2, date(2026, 5, 15))
    kwargs = mock_r2.upload.call_args.kwargs
    assert "cache_control" not in kwargs or kwargs["cache_control"] is None


def test_publicar_sidecar_serializa_json_legivel_preservando_acentos(mock_r2):
    import json as _json

    capturados: dict = {}
    mock_r2.upload.side_effect = _upload_capturando_bytes(capturados)
    sidecar = {
        "versao": 1,
        "manchete": "Contratação para licitação eletrônica em São Paulo",
        "tags": ["áudio", "energia"],
    }

    publicar_sidecar(sidecar, mock_r2, date(2026, 5, 15))

    conteudo = capturados["bytes"].decode("utf-8")
    # ensure_ascii=False mantém acentos como UTF-8 (não \uXXXX)
    assert "Contratação" in conteudo
    assert "áudio" in conteudo
    assert "\\u" not in conteudo
    # indent=2 deixa legível (quebras de linha presentes)
    assert "\n" in conteudo
    # Round-trip funciona
    assert _json.loads(conteudo) == sidecar


# =============================================================
# publicar_tudo (orquestrador)
# =============================================================


def test_publicar_tudo_chama_publicar_jornal_depois_publicar_indice(
    mock_r2, tmp_path, monkeypatch,
):
    """Ordem: jornal HTML → (sidecar JSON se existir) → índice."""
    _criar_jsons(tmp_path / "diarios", {"mprr": ["2026-05-15-961"]})
    html_path = _criar_html_falso(tmp_path)

    publicar_tudo(
        html_path,
        mock_r2,
        date(2026, 5, 15),
        diarios_dir=tmp_path / "diarios",
    )

    chaves_uploaded = [c.args[1] for c in mock_r2.upload.call_args_list]
    assert chaves_uploaded == ["jornal/2026-05-15.html", "jornal/index.html"]


def test_publicar_tudo_publica_sidecar_quando_arquivo_existe(
    mock_r2, tmp_path,
):
    """Ciclo 11.4: se sidecar JSON existe ao lado do HTML, sobe entre HTML e índice."""
    _criar_jsons(tmp_path / "diarios", {"mprr": ["2026-05-15-961"]})
    html_path = _criar_html_falso(tmp_path)
    sidecar_path = html_path.with_suffix(".json")
    sidecar_path.write_text('{"versao": 1, "materias": []}')

    publicar_tudo(
        html_path,
        mock_r2,
        date(2026, 5, 15),
        diarios_dir=tmp_path / "diarios",
    )

    chaves_uploaded = [c.args[1] for c in mock_r2.upload.call_args_list]
    assert chaves_uploaded == [
        "jornal/2026-05-15.html",
        "jornal/2026-05-15.json",
        "jornal/index.html",
    ]


def test_publicar_tudo_ignora_sidecar_ausente_para_compat(mock_r2, tmp_path):
    """Sem sidecar (pipeline antigo), publicar_tudo segue sem reclamar."""
    _criar_jsons(tmp_path / "diarios", {"mprr": ["2026-05-15-961"]})
    html_path = _criar_html_falso(tmp_path)
    # NÃO criamos sidecar_path

    publicar_tudo(
        html_path,
        mock_r2,
        date(2026, 5, 15),
        diarios_dir=tmp_path / "diarios",
    )

    chaves_uploaded = [c.args[1] for c in mock_r2.upload.call_args_list]
    assert "jornal/2026-05-15.json" not in chaves_uploaded


# =============================================================
# baixar_sidecar / agregar_destaques_recentes (Ciclo 11.7)
# =============================================================


def _sidecar_bytes(data_iso: str, materias: list[dict]) -> bytes:
    import json as _json

    return _json.dumps(
        {
            "versao": 1,
            "data_edicao": data_iso,
            "data_formatada": data_iso,
            "url_jornal": f"https://x/{data_iso}.html",
            "total_relevantes": len(materias),
            "materias": materias,
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _materia_dict(
    manchete="M",
    resumo="R",
    valor_rs=None,
    categoria="C",
    orgao="MPRR",
    pdf_url="https://x/y.pdf",
    tags=None,
):
    return {
        "orgao": orgao,
        "tipo": "EXTRATO",
        "categoria": categoria,
        "manchete": manchete,
        "resumo": resumo,
        "valor_rs": valor_rs,
        "tags": tags or [],
        "pdf_url": pdf_url,
        "pagina": None,
    }


def test_baixar_sidecar_parseia_json_quando_existe(mock_r2):
    mock_r2.download_bytes.return_value = _sidecar_bytes(
        "2026-05-15", [_materia_dict()],
    )
    d = baixar_sidecar(date(2026, 5, 15), mock_r2)
    assert d is not None
    assert d["data_edicao"] == "2026-05-15"
    mock_r2.download_bytes.assert_called_once_with("jornal/2026-05-15.json")


def test_baixar_sidecar_devolve_none_em_404(mock_r2):
    from botocore.exceptions import ClientError

    mock_r2.download_bytes.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "GetObject",
    )
    assert baixar_sidecar(date(2026, 5, 15), mock_r2) is None


def test_baixar_sidecar_devolve_none_em_NoSuchKey(mock_r2):
    from botocore.exceptions import ClientError

    mock_r2.download_bytes.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject",
    )
    assert baixar_sidecar(date(2026, 5, 15), mock_r2) is None


def test_agregar_pega_n_sidecars_mais_recentes(mock_r2):
    chamadas = []

    def fake_download(chave):
        chamadas.append(chave)
        return _sidecar_bytes("2026-05-15", [_materia_dict()])

    mock_r2.download_bytes.side_effect = fake_download
    datas = [date(2026, 5, d) for d in range(20, 5, -1)]  # 20..6
    agregar_destaques_recentes(datas, mock_r2, n_sidecars=5, k_destaques=3)
    # Só os 5 mais recentes devem ser baixados
    assert len(chamadas) == 5
    assert chamadas[0] == "jornal/2026-05-20.json"


def test_agregar_hero_e_top_por_data_e_valor(mock_r2):
    """Hero = mais recente; entre matérias do mesmo dia, maior valor."""

    def fake_download(chave):
        if "2026-05-15" in chave:
            return _sidecar_bytes(
                "2026-05-15",
                [
                    _materia_dict(manchete="MEIA", valor_rs=100.0),
                    _materia_dict(manchete="ALTA", valor_rs=999999.0),
                ],
            )
        if "2026-05-14" in chave:
            return _sidecar_bytes(
                "2026-05-14",
                [_materia_dict(manchete="OUTRA", valor_rs=500000.0)],
            )
        return _sidecar_bytes(chave[7:-5], [])

    mock_r2.download_bytes.side_effect = fake_download
    hero, grid, _ = agregar_destaques_recentes(
        [date(2026, 5, 15), date(2026, 5, 14)], mock_r2,
        n_sidecars=2, k_destaques=8,
    )
    assert hero is not None
    assert hero["manchete"] == "ALTA"


def test_agregar_grid_tem_no_maximo_k_minus_1_cards(mock_r2):
    def fake_download(chave):
        return _sidecar_bytes(
            chave[7:-5],
            [_materia_dict(manchete=f"M{i}") for i in range(5)],
        )

    mock_r2.download_bytes.side_effect = fake_download
    hero, grid, _ = agregar_destaques_recentes(
        [date(2026, 5, 15)], mock_r2, n_sidecars=1, k_destaques=3,
    )
    # hero + 2 cards no grid = 3 destaques total
    assert hero is not None
    assert len(grid) == 2


def test_agregar_trunca_resumo_a_280_chars_com_reticencias(mock_r2):
    longo = "x" * 500
    mock_r2.download_bytes.side_effect = lambda chave: _sidecar_bytes(
        chave[7:-5], [_materia_dict(manchete="M", resumo=longo)],
    )
    hero, _, _ = agregar_destaques_recentes(
        [date(2026, 5, 15)], mock_r2, n_sidecars=1, k_destaques=1,
    )
    assert len(hero["resumo"]) <= 281
    assert hero["resumo"].endswith("…")


def test_agregar_edicoes_meta_para_lista_compacta(mock_r2):
    mock_r2.download_bytes.side_effect = lambda chave: _sidecar_bytes(
        chave[7:-5],
        [_materia_dict(manchete=f"M-{chave[7:17]}")] * 2,
    )
    _, _, edicoes = agregar_destaques_recentes(
        [date(2026, 5, 15), date(2026, 5, 14)], mock_r2,
        n_sidecars=10, k_destaques=8,
    )
    assert len(edicoes) == 2
    assert all("data_edicao" in e for e in edicoes)
    assert all("data_formatada" in e for e in edicoes)
    assert all("url_jornal" in e for e in edicoes)
    assert all(e["total_relevantes"] == 2 for e in edicoes)


def test_agregar_pula_404_silenciosamente(mock_r2):
    from botocore.exceptions import ClientError

    def fake_download(chave):
        if "2026-05-15" in chave:
            return _sidecar_bytes(
                "2026-05-15", [_materia_dict(manchete="VAI")],
            )
        raise ClientError({"Error": {"Code": "404"}}, "GetObject")

    mock_r2.download_bytes.side_effect = fake_download
    hero, grid, edicoes = agregar_destaques_recentes(
        [date(2026, 5, 15), date(2026, 5, 14)], mock_r2,
        n_sidecars=2, k_destaques=8,
    )
    assert hero is not None
    assert hero["manchete"] == "VAI"
    assert len(edicoes) == 1


def test_agregar_lista_de_datas_vazia_devolve_hero_none(mock_r2):
    hero, grid, edicoes = agregar_destaques_recentes(
        [], mock_r2, n_sidecars=10, k_destaques=8,
    )
    assert hero is None
    assert grid == []
    assert edicoes == []


# =============================================================
# Template indice.html.j2 — Ciclo 11.8 (WSJ-style)
# =============================================================
#
# Testes do template direto via Jinja2 Environment (sem passar por
# gerar_indice). Ciclo 11.9 reconecta gerar_indice ao novo template.


def _render_indice(**ctx):
    from scripts.publicar import _env
    base = dict(
        hero=None,
        destaques=[],
        edicoes=[],
        total_edicoes=0,
        data_ultima_formatada=None,
    )
    base.update(ctx)
    return _env.get_template("indice.html.j2").render(**base)


def _materia_para_destaque(**overrides):
    base = dict(
        orgao="MPRR",
        tipo="EXTRATO",
        categoria="Contratação",
        manchete="Manchete teste",
        resumo="Resumo curto teste.",
        valor_rs=152340.50,
        tags=["licitação"],
        pdf_url="https://x/y.pdf",
        pagina=None,
        data_edicao="2026-05-15",
    )
    base.update(overrides)
    return base


def test_template_estrutura_basica_html_valida():
    html = _render_indice()
    assert "<!DOCTYPE html>" in html
    assert '<html lang="pt-BR">' in html
    assert "<head>" in html.lower()
    assert "</body>" in html.lower()


def test_template_define_token_cor_rule_vermelho_wsj():
    html = _render_indice()
    assert "--cor-rule" in html
    assert "#c8102e" in html


def test_template_carrega_fontes_fraunces_inter_jetbrains():
    html = _render_indice()
    assert "Fraunces" in html
    assert "Inter" in html
    assert "JetBrains+Mono" in html or "JetBrains Mono" in html


def test_template_header_wordmark_observatorio_roraima():
    html = _render_indice()
    assert "Observatório Roraima" in html


def test_template_hero_renderiza_quando_passado():
    hero = _materia_para_destaque(
        manchete="MANCHETE HERO", categoria="Investigação",
    )
    html = _render_indice(hero=hero)
    assert 'class="hero"' in html
    assert "MANCHETE HERO" in html
    assert "Investigação" in html


def test_template_hero_kicker_combina_categoria_e_orgao():
    hero = _materia_para_destaque(
        categoria="Contratação", orgao="MPRR", manchete="X",
    )
    html = _render_indice(hero=hero)
    # kicker exibe categoria e órgão (a ordem precisa estar visível)
    assert "Contratação" in html
    assert "MPRR" in html


def test_template_sem_hero_nao_renderiza_section_hero():
    html = _render_indice(hero=None)
    assert 'class="hero"' not in html


def test_template_grid_destaques_renderiza_um_card_por_item():
    grid = [
        _materia_para_destaque(manchete=f"DESTAQUE-{i}") for i in range(5)
    ]
    html = _render_indice(destaques=grid)
    assert html.count('class="card-destaque"') == 5
    for i in range(5):
        assert f"DESTAQUE-{i}" in html


def test_template_grid_destaques_vazio_nao_renderiza_secao():
    html = _render_indice(destaques=[])
    assert 'class="card-destaque"' not in html


def test_template_lista_compacta_usa_url_jornal_do_novo_schema():
    edicoes = [
        {
            "data_edicao": "2026-05-15",
            "data_formatada": "15 de maio de 2026",
            "url_jornal": "https://pub-xxx.r2.dev/jornal/2026-05-15.html",
            "total_relevantes": 7,
        },
        {
            "data_edicao": "2026-05-14",
            "data_formatada": "14 de maio de 2026",
            "url_jornal": "https://pub-xxx.r2.dev/jornal/2026-05-14.html",
            "total_relevantes": 3,
        },
    ]
    html = _render_indice(edicoes=edicoes, total_edicoes=2)
    assert 'href="https://pub-xxx.r2.dev/jornal/2026-05-15.html"' in html
    assert 'href="https://pub-xxx.r2.dev/jornal/2026-05-14.html"' in html
    assert "15 de maio de 2026" in html
    assert "14 de maio de 2026" in html


def test_template_lista_compacta_mostra_total_relevantes_quando_disponivel():
    edicoes = [
        {
            "data_edicao": "2026-05-15",
            "data_formatada": "15 de maio",
            "url_jornal": "https://x/j.html",
            "total_relevantes": 7,
        },
    ]
    html = _render_indice(edicoes=edicoes, total_edicoes=1)
    # exibe a contagem em alguma forma (ex: "7 matérias")
    assert "7" in html


def test_template_empty_state_quando_nada_disponivel():
    html = _render_indice(hero=None, destaques=[], edicoes=[], total_edicoes=0)
    # algum indicador de vazio na home
    assert "nenhuma" in html.lower() or "0 edi" in html.lower()


def test_template_valor_rs_aparece_em_formato_brl_no_hero():
    hero = _materia_para_destaque(valor_rs=987654.32, manchete="VAL")
    html = _render_indice(hero=hero)
    # 987.654,32 (formato brasileiro)
    assert "987.654,32" in html
