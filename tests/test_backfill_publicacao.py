"""Testes do backfill de publicação (Ciclo 10.6b)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts import backfill_publicacao as bp
from scripts.segmentar import Materia


def _escrever_json(diarios_dir: Path, fonte: str, nome: str, url_r2: str | None) -> None:
    d = diarios_dir / fonte
    d.mkdir(parents=True, exist_ok=True)
    conteudo: dict = {"orgao": fonte}
    if url_r2 is not None:
        conteudo["url_r2"] = url_r2
    (d / f"{nome}.json").write_text(json.dumps(conteudo), encoding="utf-8")


def _materia() -> Materia:
    return Materia(orgao="MPRR", tipo="EXTRATO", texto="x", pdf_url="y", relevante=True)


# =============================================================
# GRUPO A — mapear_chaves
# =============================================================

def test_mapear_chaves_extrai_chave_por_data_e_fonte(tmp_path):
    _escrever_json(
        tmp_path, "mprr", "2026-05-20-964",
        "https://pub.r2.dev/mprr/2026/05/2026-05-20-964.pdf",
    )
    _escrever_json(
        tmp_path, "tjrr", "2026-05-20",
        "https://pub.r2.dev/tjrr/2026/05/2026-05-20.pdf",
    )

    mapa = bp.mapear_chaves(tmp_path)

    assert mapa[date(2026, 5, 20)] == {
        "MPRR": "mprr/2026/05/2026-05-20-964.pdf",
        "TJRR": "tjrr/2026/05/2026-05-20.pdf",
    }


def test_mapear_chaves_agrupa_datas_distintas(tmp_path):
    _escrever_json(tmp_path, "mprr", "2026-05-19-963", "https://p/mprr/a.pdf")
    _escrever_json(tmp_path, "mprr", "2026-05-20-964", "https://p/mprr/b.pdf")

    mapa = bp.mapear_chaves(tmp_path)

    assert set(mapa.keys()) == {date(2026, 5, 19), date(2026, 5, 20)}


def test_mapear_chaves_ignora_json_sem_url_r2(tmp_path):
    _escrever_json(tmp_path, "mprr", "2026-05-20-964", None)
    assert bp.mapear_chaves(tmp_path) == {}


def test_mapear_chaves_dir_inexistente_retorna_vazio(tmp_path):
    assert bp.mapear_chaves(tmp_path / "nao-existe") == {}


# =============================================================
# GRUPO B — processar_data (gera + publica a partir de chaves)
# =============================================================

@pytest.fixture
def mocks(monkeypatch):
    r2 = MagicMock()
    r2.existe.return_value = False
    pc = MagicMock(return_value=[])
    pub = MagicMock(return_value="https://pub/jornal/x.html")
    rend = MagicMock(return_value="<html>jornal</html>")
    monkeypatch.setattr(bp, "processar_chave", pc)
    monkeypatch.setattr(bp, "publicar_jornal", pub)
    monkeypatch.setattr(bp, "renderizar_jornal", rend)
    return {
        "r2": r2, "processar_chave": pc, "publicar_jornal": pub,
        "renderizar_jornal": rend,
    }


def test_processar_data_pula_se_jornal_ja_existe(mocks, tmp_path):
    mocks["r2"].existe.return_value = True

    status, n = bp.processar_data(
        date(2026, 5, 20), {"MPRR": "mprr/x.pdf"},
        mocks["r2"], MagicMock(), tmp_path,
    )

    assert status == "pulado_dedupe"
    assert n == 0
    mocks["processar_chave"].assert_not_called()
    mocks["publicar_jornal"].assert_not_called()


def test_processar_data_consulta_chave_jornal_no_padrao(mocks, tmp_path):
    bp.processar_data(
        date(2026, 5, 20), {"MPRR": "mprr/x.pdf"},
        mocks["r2"], MagicMock(), tmp_path,
    )
    mocks["r2"].existe.assert_called_once_with("jornal/2026-05-20.html")


def test_processar_data_gera_publica_e_conta_materias(mocks, tmp_path):
    mocks["processar_chave"].return_value = [_materia()]

    status, n = bp.processar_data(
        date(2026, 5, 20), {"MPRR": "mprr/x.pdf", "TJRR": "tjrr/y.pdf"},
        mocks["r2"], MagicMock(), tmp_path,
    )

    assert status == "sucesso"
    assert n == 2  # processar_chave chamado por fonte, 1 matéria cada
    assert mocks["processar_chave"].call_count == 2
    mocks["publicar_jornal"].assert_called_once()
    assert (tmp_path / "2026-05-20.html").exists()


def test_processar_data_sem_materias_ainda_publica(mocks, tmp_path):
    mocks["processar_chave"].return_value = []

    status, n = bp.processar_data(
        date(2026, 5, 20), {"MPRR": "mprr/x.pdf"},
        mocks["r2"], MagicMock(), tmp_path,
    )

    assert status == "sucesso"
    assert n == 0
    mocks["publicar_jornal"].assert_called_once()
