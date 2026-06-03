"""Testes do CLI backfill_sidecars (Ciclo 11.6)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.backfill_sidecars import (
    backfill_uma,
    listar_edicoes_publicadas,
    main,
)


_HTML_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "jornal_sample.html"
)


@pytest.fixture
def html_sample_bytes() -> bytes:
    return _HTML_FIXTURE_PATH.read_bytes()


@pytest.fixture
def mock_r2(html_sample_bytes):
    """R2Client mock com list_objects_v2 + download_bytes prontos."""
    r2 = MagicMock()
    r2.client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "jornal/2026-05-15.html"},
            {"Key": "jornal/2026-05-14.html"},
            {"Key": "jornal/index.html"},
            {"Key": "jornal/2026-05-15.json"},  # já existe — sidecar
        ],
    }
    r2.download_bytes.return_value = html_sample_bytes
    r2.existe.return_value = False
    r2.public_domain = "pub-xxx.r2.dev"
    r2.url_publica.side_effect = (
        lambda chave: f"https://pub-xxx.r2.dev/{chave}"
    )
    r2.upload.side_effect = (
        lambda caminho, chave, *a, **kw: f"https://pub-xxx.r2.dev/{chave}"
    )
    return r2


# ============================================================
# listar_edicoes_publicadas
# ============================================================


def test_lista_apenas_html_de_edicoes_nao_indice_nem_json(mock_r2):
    datas = listar_edicoes_publicadas(mock_r2)
    assert date(2026, 5, 15) in datas
    assert date(2026, 5, 14) in datas
    # index.html não conta como edição
    assert len(datas) == 2


def test_ordenado_descendente(mock_r2):
    datas = listar_edicoes_publicadas(mock_r2)
    assert datas == sorted(datas, reverse=True)


def test_chama_list_objects_v2_com_prefixo_jornal(mock_r2):
    listar_edicoes_publicadas(mock_r2)
    kwargs = mock_r2.client.list_objects_v2.call_args.kwargs
    assert kwargs["Prefix"] == "jornal/"


def test_lista_vazia_quando_bucket_sem_jornais():
    r2 = MagicMock()
    r2.client.list_objects_v2.return_value = {}
    assert listar_edicoes_publicadas(r2) == []


# ============================================================
# backfill_uma
# ============================================================


def test_backfill_uma_baixa_parseia_sobe(mock_r2):
    status = backfill_uma(date(2026, 5, 15), mock_r2)
    assert status == "sucesso"
    mock_r2.download_bytes.assert_called_once_with("jornal/2026-05-15.html")
    # publicar_sidecar usou r2.upload com chave .json
    chaves_uploaded = [c.args[1] for c in mock_r2.upload.call_args_list]
    assert "jornal/2026-05-15.json" in chaves_uploaded


def test_backfill_uma_skip_quando_json_ja_existe(mock_r2):
    mock_r2.existe.return_value = True  # sidecar já no R2
    status = backfill_uma(date(2026, 5, 15), mock_r2, skip_existentes=True)
    assert status == "ja_existe"
    mock_r2.download_bytes.assert_not_called()
    mock_r2.upload.assert_not_called()


def test_backfill_uma_skip_false_reprocessa_mesmo_existente(mock_r2):
    mock_r2.existe.return_value = True
    status = backfill_uma(date(2026, 5, 15), mock_r2, skip_existentes=False)
    assert status == "sucesso"
    mock_r2.download_bytes.assert_called_once()


def test_backfill_uma_dry_run_nao_chama_upload(mock_r2):
    status = backfill_uma(date(2026, 5, 15), mock_r2, dry_run=True)
    assert status == "dry_run"
    mock_r2.upload.assert_not_called()


# ============================================================
# main (CLI orquestrador)
# ============================================================


def test_main_processa_todas_edicoes_listadas(mock_r2, monkeypatch):
    monkeypatch.setattr(
        "scripts.backfill_sidecars.R2Client.from_env", lambda: mock_r2,
    )
    rc = main([])
    assert rc == 0
    chaves = [c.args[1] for c in mock_r2.upload.call_args_list]
    assert "jornal/2026-05-15.json" in chaves
    assert "jornal/2026-05-14.json" in chaves


def test_main_limite_corta_apos_n(mock_r2, monkeypatch):
    monkeypatch.setattr(
        "scripts.backfill_sidecars.R2Client.from_env", lambda: mock_r2,
    )
    rc = main(["--limite", "1"])
    assert rc == 0
    chaves = [c.args[1] for c in mock_r2.upload.call_args_list]
    # ordem desc → primeiro é 2026-05-15
    assert chaves == ["jornal/2026-05-15.json"]


def test_main_dry_run_nao_chama_upload(mock_r2, monkeypatch):
    monkeypatch.setattr(
        "scripts.backfill_sidecars.R2Client.from_env", lambda: mock_r2,
    )
    rc = main(["--dry-run"])
    assert rc == 0
    mock_r2.upload.assert_not_called()
