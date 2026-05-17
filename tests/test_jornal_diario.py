"""Testes do orquestrador de jornal diário (Ciclo 9.1)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
        "coletar_dia": MagicMock(return_value=True),
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
    mock_pipeline["r2_instance"].existe.side_effect = [False, True, False, True]
    monkeypatch_obj = pytest.MonkeyPatch()
    try:
        monkeypatch_obj.setattr(
            "scripts.jornal_diario.coletar_dia",
            mock_pipeline["coletar_dia"],
        )
        gerar_jornal_diario(date(2026, 4, 30), output_dir=tmp_path)
        assert mock_pipeline["coletar_dia"].called
    finally:
        monkeypatch_obj.undo()


def test_coletor_falha_fonte_e_pulada_jornal_continua(mock_pipeline, tmp_path):
    existe_calls = {"contador": 0}

    def existe_side_effect(*args, **kwargs):
        existe_calls["contador"] += 1
        return False

    mock_pipeline["r2_instance"].existe.side_effect = existe_side_effect
    mock_pipeline["coletar_dia"].return_value = False
    monkeypatch_obj = pytest.MonkeyPatch()
    try:
        monkeypatch_obj.setattr(
            "scripts.jornal_diario.coletar_dia",
            mock_pipeline["coletar_dia"],
        )
        resultado = gerar_jornal_diario(
            date(2026, 4, 30), output_dir=tmp_path,
        )
        assert resultado.exists()
    finally:
        monkeypatch_obj.undo()


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
