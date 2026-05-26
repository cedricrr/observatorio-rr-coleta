"""Testes do orquestrador de jornal diário (Ciclo 9.1)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts import jornal_diario as jd
from scripts.jornal_diario import gerar_jornal_diario
from scripts.segmentar import Materia


def _materia_classificada(
    orgao: str = "MPRR",
    manchete: str = "Manchete teste",
    relevante: bool = True,
) -> Materia:
    return Materia(
        orgao=orgao,
        tipo="EXTRATO_CONTRATO",
        texto="texto bruto",
        pdf_url=f"https://example.com/{orgao.lower()}.pdf",
        categoria="Contratos e licitações",
        manchete=manchete,
        resumo="Resumo da matéria.",
        valor_rs=100000.00,
        tags=["test"],
        relevante=relevante,
    )


def _coletar_dia_default(fonte_codigo, data_alvo, r2):
    """Side_effect default da fixture: monta chave R2 fake por fonte."""
    return (
        f"{fonte_codigo.lower()}/{data_alvo.year}/"
        f"{data_alvo.month:02d}/{data_alvo.isoformat()}-fake.pdf"
    )


@pytest.fixture
def mock_pipeline(monkeypatch, tmp_path):
    """Mocka todas as dependências externas do pipeline.

    Retorna dict com mocks pra cada estágio. Testes podem
    customizar comportamento via return_value/side_effect.
    """
    mocks = {
        "r2_client_class": MagicMock(),
        "baixar_pdf": MagicMock(return_value=b"%PDF-fake"),
        "pdf_para_markdown": MagicMock(return_value="# Markdown fake"),
        "segmentar_materias": MagicMock(return_value=[]),
        "filtrar_materias": MagicMock(return_value=[]),
        "classificar_materia": MagicMock(side_effect=lambda m, c: m),
        "cliente_anthropic_class": MagicMock(),
        "coletar_dia": MagicMock(side_effect=_coletar_dia_default),
    }

    r2_instance = MagicMock()
    r2_instance.existe.return_value = True
    mocks["r2_client_class"].from_env.return_value = r2_instance
    mocks["r2_instance"] = r2_instance

    monkeypatch.setattr(
        "scripts.jornal_diario.R2Client", mocks["r2_client_class"]
    )
    monkeypatch.setattr(
        "scripts.jornal_diario.baixar_pdf_do_r2", mocks["baixar_pdf"]
    )
    monkeypatch.setattr(
        "scripts.jornal_diario.pdf_para_markdown",
        mocks["pdf_para_markdown"],
    )
    monkeypatch.setattr(
        "scripts.jornal_diario.segmentar_materias",
        mocks["segmentar_materias"],
    )
    monkeypatch.setattr(
        "scripts.jornal_diario.filtrar_materias",
        mocks["filtrar_materias"],
    )
    monkeypatch.setattr(
        "scripts.jornal_diario.classificar_materia",
        mocks["classificar_materia"],
    )
    monkeypatch.setattr(
        "scripts.jornal_diario.ClienteAnthropic",
        mocks["cliente_anthropic_class"],
    )
    monkeypatch.setattr(
        "scripts.jornal_diario.coletar_dia", mocks["coletar_dia"]
    )

    return mocks


# =============================================================
# GRUPO A — Caso feliz com mocks
# =============================================================


def test_gera_jornal_com_mprr_e_tjrr(mock_pipeline, tmp_path):
    mock_pipeline["filtrar_materias"].return_value = [
        _materia_classificada(orgao="MPRR", relevante=True),
    ]
    resultado = gerar_jornal_diario(
        date(2026, 4, 30),
        output_dir=tmp_path,
    )
    assert isinstance(resultado, Path)
    assert resultado.exists()
    assert resultado.suffix == ".html"
    assert "2026-04-30" in resultado.name
    html = resultado.read_text()
    assert "Manchete teste" in html


def test_filtra_apenas_uma_fonte(mock_pipeline, tmp_path):
    gerar_jornal_diario(
        date(2026, 4, 30),
        fontes=["MPRR"],
        output_dir=tmp_path,
    )
    chaves_chamadas = [
        call.args[0] for call in mock_pipeline["baixar_pdf"].call_args_list
    ]
    assert all("tjrr" not in c.lower() for c in chaves_chamadas)
    assert any("mprr" in c.lower() for c in chaves_chamadas)


def test_output_dir_customizado(mock_pipeline, tmp_path):
    custom = tmp_path / "subpasta"
    resultado = gerar_jornal_diario(
        date(2026, 4, 30), output_dir=custom,
    )
    assert resultado.parent == custom
    assert custom.exists()


def test_retorna_path_arquivo_existente(mock_pipeline, tmp_path):
    resultado = gerar_jornal_diario(date(2026, 4, 30), output_dir=tmp_path)
    assert resultado.is_file()
    assert resultado.stat().st_size > 0


def test_classificacao_de_uma_materia_falha_pula_e_continua(
    mock_pipeline, tmp_path,
):
    m1 = _materia_classificada(orgao="MPRR", manchete="VAI_FALHAR")
    m2 = _materia_classificada(orgao="MPRR", manchete="VAI_PASSAR")
    mock_pipeline["filtrar_materias"].return_value = [m1, m2]
    mock_pipeline["classificar_materia"].side_effect = [
        ValueError("erro de classificação"),
        m2,
    ]
    resultado = gerar_jornal_diario(date(2026, 4, 30), output_dir=tmp_path)
    html = resultado.read_text()
    assert "VAI_FALHAR" not in html
    assert "VAI_PASSAR" in html


# =============================================================
# GRUPO B — Coleta inline
# =============================================================


def test_pdf_nao_no_r2_dispara_coletor(mock_pipeline, tmp_path):
    """coletar_dia é sempre chamado por _processar_fonte.

    Após o refactor, _processar_fonte não verifica r2.existe antes
    de chamar coletar_dia. processar_fonte do scripts.coletar já
    faz dedup internamente. Assim, coletar_dia é invocado uma vez
    por fonte sempre.
    """
    gerar_jornal_diario(date(2026, 4, 30), output_dir=tmp_path)
    assert mock_pipeline["coletar_dia"].call_count == 2


def test_coletor_falha_fonte_e_pulada_jornal_continua(
    mock_pipeline, tmp_path,
):
    """Quando coletar_dia retorna None, fonte é pulada e o pipeline
    NÃO chega a baixar PDF nem processar.

    Esse teste valida explicitamente que a lógica de fix está
    exercida: se coletar_dia falhar, baixar_pdf não é nem tentado.
    """
    mock_pipeline["coletar_dia"].side_effect = lambda *a, **kw: None
    resultado = gerar_jornal_diario(
        date(2026, 4, 30), output_dir=tmp_path,
    )
    assert mock_pipeline["coletar_dia"].call_count >= 1
    assert mock_pipeline["baixar_pdf"].call_count == 0
    assert resultado.exists()
    html = resultado.read_text()
    assert "Nenhuma matéria" in html


def test_nenhuma_materia_disponivel_gera_jornal_vazio(
    mock_pipeline, tmp_path,
):
    mock_pipeline["filtrar_materias"].return_value = []
    resultado = gerar_jornal_diario(
        date(2026, 4, 30), output_dir=tmp_path,
    )
    assert resultado.exists()
    html = resultado.read_text()
    assert "Nenhuma matéria" in html


# =============================================================
# GRUPO C — Validação de entradas
# =============================================================


def test_fonte_invalida_levanta_valueerror(mock_pipeline, tmp_path):
    with pytest.raises(ValueError, match="fonte"):
        gerar_jornal_diario(
            date(2026, 4, 30),
            fontes=["FOO"],
            output_dir=tmp_path,
        )


def test_data_futura_levanta_valueerror(mock_pipeline, tmp_path):
    with pytest.raises(ValueError, match="data"):
        gerar_jornal_diario(
            date(2099, 1, 1), output_dir=tmp_path,
        )


# =============================================================
# GRUPO D — Defaults
# =============================================================


def test_fontes_default_inclui_mprr_e_tjrr(mock_pipeline, tmp_path):
    gerar_jornal_diario(date(2026, 4, 30), output_dir=tmp_path)
    chaves = [
        call.args[0] for call in mock_pipeline["baixar_pdf"].call_args_list
    ]
    assert any("mprr" in c.lower() for c in chaves)
    assert any("tjrr" in c.lower() for c in chaves)


def test_output_dir_default_e_tmp_observatorio(mock_pipeline):
    resultado = gerar_jornal_diario(date(2026, 4, 30))
    assert "tmp" in str(resultado).lower()
    assert "observatorio" in str(resultado).lower()
    if resultado.exists():
        resultado.unlink()


def test_pdf_url_usa_url_publica_do_r2(mock_pipeline, tmp_path):
    """pdf_url passado para segmentar_materias deve vir de r2.url_publica,
    não de placeholder example.com.

    O leitor do jornal precisa do link real para o R2 para verificar
    a matéria contra o documento oficial.
    """
    mock_pipeline["r2_instance"].url_publica.return_value = (
        "https://files.pub.dev/observatorio-real/mprr/x.pdf"
    )
    gerar_jornal_diario(
        date(2026, 4, 30),
        fontes=["MPRR"],
        output_dir=tmp_path,
    )
    seg_calls = mock_pipeline["segmentar_materias"].call_args_list
    assert len(seg_calls) == 1
    pdf_url_arg = seg_calls[0].args[2]
    assert "files.pub.dev" in pdf_url_arg
    assert "example.com" not in pdf_url_arg


# =============================================================
# GRUPO E — processar_chave: pipeline a partir da chave (Ciclo 10.6a)
# =============================================================
# Caminho de publicação que NÃO re-coleta — usa a chave R2 já conhecida
# (vinda dos JSONs locais no backfill 10.6b). Evita re-discover nos portais
# (que falharia para datas antigas, gerando jornal vazio mesmo com PDF no R2).


def test_processar_chave_nao_recoleta(mock_pipeline):
    mock_pipeline["filtrar_materias"].return_value = [
        _materia_classificada(orgao="MPRR", relevante=True),
    ]
    chave = "mprr/2026/04/2026-04-30-939.pdf"

    materias = jd.processar_chave(
        chave, "MPRR", mock_pipeline["r2_instance"], MagicMock(),
    )

    assert len(materias) == 1
    # NÃO chama coletar_dia (sem discover nos portais)
    assert mock_pipeline["coletar_dia"].call_count == 0
    # usa a chave fornecida diretamente no download
    assert mock_pipeline["baixar_pdf"].call_args.args[0] == chave


def test_processar_chave_usa_url_publica_da_chave(mock_pipeline):
    mock_pipeline["r2_instance"].url_publica.return_value = "https://pub/x.pdf"

    jd.processar_chave(
        "mprr/x.pdf", "MPRR", mock_pipeline["r2_instance"], MagicMock(),
    )

    seg_calls = mock_pipeline["segmentar_materias"].call_args_list
    assert seg_calls[0].args[2] == "https://pub/x.pdf"


def test_processar_chave_pipeline_falha_retorna_vazio(mock_pipeline):
    mock_pipeline["baixar_pdf"].side_effect = RuntimeError("R2 down")

    materias = jd.processar_chave(
        "mprr/x.pdf", "MPRR", mock_pipeline["r2_instance"], MagicMock(),
    )

    assert materias == []


def test_processar_chave_classificacao_de_uma_materia_falha_continua(mock_pipeline):
    m1 = _materia_classificada(orgao="MPRR", manchete="FALHA")
    m2 = _materia_classificada(orgao="MPRR", manchete="OK")
    mock_pipeline["filtrar_materias"].return_value = [m1, m2]
    mock_pipeline["classificar_materia"].side_effect = [
        ValueError("classificação falhou"),
        m2,
    ]

    materias = jd.processar_chave(
        "mprr/x.pdf", "MPRR", mock_pipeline["r2_instance"], MagicMock(),
    )

    manchetes = [m.manchete for m in materias]
    assert "OK" in manchetes
    assert "FALHA" not in manchetes
