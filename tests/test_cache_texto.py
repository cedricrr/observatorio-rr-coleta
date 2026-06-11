"""Testes do scripts.cache_texto (cache de extração de texto no R2)."""

import json
from pathlib import Path

import fitz
import pytest

from scripts.backfill import Checkpoint, carregar_checkpoint, marcar_processado
from scripts.cache_texto import (
    backfill_texto,
    chave_texto,
    extrair_e_gravar,
    listar_metadados,
    main,
    montar_documento,
)


def _checkpoint() -> Checkpoint:
    return Checkpoint(
        escopo="texto-todas",
        iniciado_em="2026-06-10T00:00:00",
        atualizado_em="2026-06-10T00:00:00",
        itens=[],
        config={},
    )


def _criar_diarios_dir(tmp_path: Path) -> Path:
    diarios = tmp_path / "diarios"
    (diarios / "mprr").mkdir(parents=True)
    (diarios / "tjrr").mkdir(parents=True)
    (diarios / "mprr" / "2022-04-26-4.json").write_text(
        json.dumps(_metadados_mprr()), encoding="utf-8"
    )
    (diarios / "tjrr" / "2022-04-11.json").write_text(
        json.dumps(
            _metadados_mprr(
                orgao="tjrr",
                numero=None,
                data_edicao="2022-04-11",
                url_r2="https://pub-xyz.r2.dev/tjrr/2022/04/2022-04-11.pdf",
            )
        ),
        encoding="utf-8",
    )
    return diarios


def _pdf_bytes(*paginas_texto: str) -> bytes:
    doc = fitz.open()
    for txt in paginas_texto:
        page = doc.new_page()
        page.insert_text((50, 100), txt)
    return doc.tobytes()


def _metadados_mprr(**extras) -> dict:
    base = {
        "orgao": "mprr",
        "data_edicao": "2022-04-26",
        "numero": 4,
        "sha256": "abc123",
        "tamanho": 1872252,
        "url_original": "https://www.mprr.mp.br/...pdf",
        "url_r2": "https://pub-xyz.r2.dev/mprr/2022/04/2022-04-26-4.pdf",
        "url_wayback": None,
        "ja_existia": False,
    }
    base.update(extras)
    return base


def test_chave_texto_com_numero():
    assert (
        chave_texto("mprr/2022/04/2022-04-26-4.pdf")
        == "texto/mprr/2022/04/2022-04-26-4.json"
    )


def test_chave_texto_sem_numero():
    assert (
        chave_texto("tjrr/2022/04/2022-04-11.pdf")
        == "texto/tjrr/2022/04/2022-04-11.json"
    )


def test_chave_texto_rejeita_chave_sem_extensao_pdf():
    with pytest.raises(ValueError):
        chave_texto("mprr/2022/04/2022-04-26.json")


def test_chave_texto_rejeita_chave_vazia():
    with pytest.raises(ValueError):
        chave_texto("")


def test_montar_documento_schema_completo():
    doc = montar_documento(
        _metadados_mprr(),
        ["texto integral da página um do diário", "texto integral da página dois do diário"],
    )

    assert doc["versao"] == 1
    assert doc["orgao"] == "mprr"
    assert doc["data_edicao"] == "2022-04-26"
    assert doc["numero"] == 4
    assert doc["chave_pdf"] == "mprr/2022/04/2022-04-26-4.pdf"
    assert doc["sha256_pdf"] == "abc123"
    assert doc["extraido_em"]  # ISO não-vazio
    assert doc["extrator"].startswith("pymupdf-")
    assert doc["total_paginas"] == 2
    assert doc["paginas_vazias"] == 0
    assert doc["paginas"] == [
        {"n": 1, "texto": "texto integral da página um do diário"},
        {"n": 2, "texto": "texto integral da página dois do diário"},
    ]


def test_montar_documento_numero_null_tjrr():
    metadados = _metadados_mprr(
        orgao="tjrr",
        numero=None,
        url_r2="https://pub-xyz.r2.dev/tjrr/2022/04/2022-04-11.pdf",
        data_edicao="2022-04-11",
    )

    doc = montar_documento(metadados, ["conteúdo"])

    assert doc["numero"] is None
    assert doc["chave_pdf"] == "tjrr/2022/04/2022-04-11.pdf"


def test_montar_documento_conta_paginas_vazias():
    paginas = ["texto longo o suficiente para não ser vazio", "   \n ", "ab"]

    doc = montar_documento(_metadados_mprr(), paginas)

    assert doc["total_paginas"] == 3
    assert doc["paginas_vazias"] == 2


def test_montar_documento_unicode_preservado():
    doc = montar_documento(_metadados_mprr(), ["Diário Eletrônico — São Luiz do Anauá"])

    assert "Anauá" in doc["paginas"][0]["texto"]


def test_extrair_e_gravar_dedupe_quando_texto_ja_existe(mocker):
    r2 = mocker.MagicMock()
    r2.existe.return_value = True

    status, _ = extrair_e_gravar(_metadados_mprr(), r2)

    assert status == "pulado_dedupe"
    r2.existe.assert_called_once_with("texto/mprr/2022/04/2022-04-26-4.json")
    r2.download_bytes.assert_not_called()
    r2.upload.assert_not_called()


def test_extrair_e_gravar_sucesso_sobe_json_imutavel(mocker):
    r2 = mocker.MagicMock()
    r2.existe.return_value = False
    r2.download_bytes.return_value = _pdf_bytes(
        "Portaria nomeando João da Silva", "Extrato de contrato"
    )
    conteudos: list[dict] = []
    r2.upload.side_effect = lambda caminho, *a, **kw: conteudos.append(
        json.loads(Path(caminho).read_text(encoding="utf-8"))
    )

    status, detalhes = extrair_e_gravar(_metadados_mprr(), r2)

    assert status == "sucesso"
    assert "2 paginas" in detalhes
    args, kwargs = r2.upload.call_args
    assert args[1] == "texto/mprr/2022/04/2022-04-26-4.json"
    assert kwargs["content_type"] == "application/json"
    assert kwargs["metadados"] == {"data-edicao": "2022-04-26"}
    assert "cache_control" not in kwargs or kwargs["cache_control"] is None
    doc = conteudos[0]
    assert doc["versao"] == 1
    assert doc["chave_pdf"] == "mprr/2022/04/2022-04-26-4.pdf"
    assert doc["total_paginas"] == 2
    assert "João da Silva" in doc["paginas"][0]["texto"]


def test_extrair_e_gravar_sobrescrever_ignora_dedupe(mocker):
    r2 = mocker.MagicMock()
    r2.existe.return_value = True
    r2.download_bytes.return_value = _pdf_bytes("Conteúdo da edição")
    r2.upload.side_effect = lambda caminho, *a, **kw: None

    status, _ = extrair_e_gravar(_metadados_mprr(), r2, sobrescrever=True)

    assert status == "sucesso"
    r2.upload.assert_called_once()


def test_extrair_e_gravar_temporario_removido_apos_upload(mocker):
    r2 = mocker.MagicMock()
    r2.existe.return_value = False
    r2.download_bytes.return_value = _pdf_bytes("Conteúdo da edição")
    caminhos: list[Path] = []
    r2.upload.side_effect = lambda caminho, *a, **kw: caminhos.append(Path(caminho))

    extrair_e_gravar(_metadados_mprr(), r2)

    assert not caminhos[0].exists()


def test_listar_metadados_todas_ordenado(tmp_path):
    diarios = _criar_diarios_dir(tmp_path)

    lista = listar_metadados(diarios, "todas")

    assert [m["orgao"] for m in lista] == ["mprr", "tjrr"]


def test_listar_metadados_filtra_por_orgao(tmp_path):
    diarios = _criar_diarios_dir(tmp_path)

    lista = listar_metadados(diarios, "tjrr")

    assert len(lista) == 1
    assert lista[0]["orgao"] == "tjrr"


def test_backfill_texto_marca_sucesso_e_persiste(tmp_path, mocker):
    extrair = mocker.patch(
        "scripts.cache_texto.extrair_e_gravar",
        return_value=("sucesso", "2 paginas, 0 vazias"),
    )
    r2 = mocker.MagicMock()
    checkpoint = _checkpoint()
    caminho_ckpt = tmp_path / "texto-todas.json"
    lista = listar_metadados(_criar_diarios_dir(tmp_path), "todas")

    backfill_texto(
        lista, r2, checkpoint, pausa=0, caminho_checkpoint=caminho_ckpt,
    )

    assert extrair.call_count == 2
    persistido = carregar_checkpoint(caminho_ckpt)
    assert len(persistido.itens) == 2
    assert {i["status"] for i in persistido.itens} == {"sucesso"}
    assert persistido.itens[0]["id"] == "mprr/2022/04/2022-04-26-4.pdf"


def test_backfill_texto_retomada_pula_processados(tmp_path, mocker):
    extrair = mocker.patch(
        "scripts.cache_texto.extrair_e_gravar", return_value=("sucesso", None),
    )
    r2 = mocker.MagicMock()
    checkpoint = _checkpoint()
    marcar_processado(checkpoint, "mprr/2022/04/2022-04-26-4.pdf", "sucesso")
    lista = listar_metadados(_criar_diarios_dir(tmp_path), "todas")

    backfill_texto(lista, r2, checkpoint, pausa=0)

    assert extrair.call_count == 1  # só o tjrr


def test_backfill_texto_dry_run_nao_toca_r2(tmp_path, mocker):
    extrair = mocker.patch("scripts.cache_texto.extrair_e_gravar")
    checkpoint = _checkpoint()
    lista = listar_metadados(_criar_diarios_dir(tmp_path), "todas")

    backfill_texto(lista, None, checkpoint, pausa=0, dry_run=True)

    extrair.assert_not_called()
    assert {i["status"] for i in checkpoint.itens} == {"pulado_dedupe"}


def test_backfill_texto_erro_marca_e_continua(tmp_path, mocker):
    mocker.patch(
        "scripts.cache_texto.extrair_e_gravar",
        side_effect=[RuntimeError("PDF corrompido"), ("sucesso", None)],
    )
    r2 = mocker.MagicMock()
    checkpoint = _checkpoint()
    lista = listar_metadados(_criar_diarios_dir(tmp_path), "todas")

    backfill_texto(lista, r2, checkpoint, pausa=0)

    status = [i["status"] for i in checkpoint.itens]
    assert status == ["erro", "sucesso"]
    assert "PDF corrompido" in checkpoint.itens[0]["detalhes"]


def test_cli_dry_run_cria_checkpoint_e_sai_zero(tmp_path):
    diarios = _criar_diarios_dir(tmp_path)
    ckpt_dir = tmp_path / "backfill"

    codigo = main([
        "--backfill",
        "--dry-run",
        "--diarios-dir", str(diarios),
        "--checkpoint-dir", str(ckpt_dir),
    ])

    assert codigo == 0
    persistido = carregar_checkpoint(ckpt_dir / "texto-todas.json")
    assert len(persistido.itens) == 2


def test_cli_retomar_nao_reprocessa(tmp_path):
    diarios = _criar_diarios_dir(tmp_path)
    ckpt_dir = tmp_path / "backfill"
    main([
        "--backfill", "--dry-run",
        "--diarios-dir", str(diarios), "--checkpoint-dir", str(ckpt_dir),
    ])

    codigo = main([
        "--backfill", "--dry-run", "--retomar",
        "--diarios-dir", str(diarios), "--checkpoint-dir", str(ckpt_dir),
    ])

    assert codigo == 0
    persistido = carregar_checkpoint(ckpt_dir / "texto-todas.json")
    assert len(persistido.itens) == 2  # nada duplicado
