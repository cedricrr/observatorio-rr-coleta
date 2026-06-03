"""Testes do publicador de jornal/índice no R2 (Ciclo 9.4)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.publicar import (
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
