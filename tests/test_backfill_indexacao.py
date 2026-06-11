"""Testes do scripts.backfill_indexacao (texto/ no R2 → POST /indexar)."""

import pytest
import requests

from scripts.backfill import Checkpoint, carregar_checkpoint, marcar_processado
from scripts.backfill_indexacao import (
    backfill_indexacao,
    indexar_chave,
    main,
    postar_documento,
)

CHAVES = [
    "texto/mprr/2022/04/2022-04-26-4.json",
    "texto/tjrr/2022/04/2022-04-11.json",
]


def _checkpoint() -> Checkpoint:
    return Checkpoint(
        escopo="indexacao",
        iniciado_em="2026-06-10T00:00:00",
        atualizado_em="2026-06-10T00:00:00",
        itens=[],
        config={},
    )


def _resposta_ok(mocker, corpo=None):
    resposta = mocker.MagicMock()
    resposta.json.return_value = corpo or {"indexadas": 5}
    resposta.raise_for_status.return_value = None
    return resposta


def test_postar_documento_envia_bearer_e_corpo(mocker):
    post = mocker.patch("requests.post", return_value=_resposta_ok(mocker))

    resultado = postar_documento("https://api.example/", "tok-123", b'{"versao": 1}')

    assert resultado == {"indexadas": 5}
    args, kwargs = post.call_args
    assert args[0] == "https://api.example/indexar"
    assert kwargs["headers"]["Authorization"] == "Bearer tok-123"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["data"] == b'{"versao": 1}'
    assert kwargs["timeout"] == 120


def test_postar_documento_faz_um_retry_em_falha_de_rede(mocker):
    post = mocker.patch(
        "requests.post",
        side_effect=[requests.ConnectionError("caiu"), _resposta_ok(mocker)],
    )

    resultado = postar_documento("https://api.example", "tok", b"{}")

    assert resultado == {"indexadas": 5}
    assert post.call_count == 2


def test_postar_documento_duas_falhas_levanta(mocker):
    mocker.patch(
        "requests.post",
        side_effect=[requests.Timeout("1"), requests.Timeout("2")],
    )

    with pytest.raises(requests.Timeout):
        postar_documento("https://api.example", "tok", b"{}")


def test_postar_documento_http_500_conta_como_falha(mocker):
    resposta_erro = mocker.MagicMock()
    resposta_erro.raise_for_status.side_effect = requests.HTTPError("500")
    post = mocker.patch(
        "requests.post", side_effect=[resposta_erro, _resposta_ok(mocker)],
    )

    resultado = postar_documento("https://api.example", "tok", b"{}")

    assert resultado == {"indexadas": 5}
    assert post.call_count == 2


def test_indexar_chave_baixa_do_r2_e_posta(mocker):
    r2 = mocker.MagicMock()
    r2.download_bytes.return_value = b'{"versao": 1}'
    postar = mocker.patch(
        "scripts.backfill_indexacao.postar_documento",
        return_value={"indexadas": 38},
    )

    status, detalhes = indexar_chave(
        "texto/mprr/2022/04/2022-04-26-4.json", r2, "https://api.example", "tok",
    )

    assert status == "sucesso"
    assert "38" in detalhes
    r2.download_bytes.assert_called_once_with("texto/mprr/2022/04/2022-04-26-4.json")
    postar.assert_called_once_with("https://api.example", "tok", b'{"versao": 1}')


def test_backfill_indexacao_marca_sucesso_e_persiste(tmp_path, mocker):
    indexar = mocker.patch(
        "scripts.backfill_indexacao.indexar_chave",
        return_value=("sucesso", "5 paginas indexadas"),
    )
    r2 = mocker.MagicMock()
    caminho_ckpt = tmp_path / "indexacao.json"

    backfill_indexacao(
        CHAVES, r2, "https://api.example", "tok", _checkpoint(),
        pausa=0, caminho_checkpoint=caminho_ckpt,
    )

    assert indexar.call_count == 2
    persistido = carregar_checkpoint(caminho_ckpt)
    assert [i["status"] for i in persistido.itens] == ["sucesso", "sucesso"]
    assert persistido.itens[0]["id"] == CHAVES[0]


def test_backfill_indexacao_erro_marca_e_continua(mocker):
    mocker.patch(
        "scripts.backfill_indexacao.indexar_chave",
        side_effect=[requests.Timeout("estourou"), ("sucesso", None)],
    )
    checkpoint = _checkpoint()

    backfill_indexacao(
        CHAVES, mocker.MagicMock(), "https://api.example", "tok", checkpoint, pausa=0,
    )

    assert [i["status"] for i in checkpoint.itens] == ["erro", "sucesso"]
    assert "estourou" in checkpoint.itens[0]["detalhes"]


def test_backfill_indexacao_retomada_pula_processados(mocker):
    indexar = mocker.patch(
        "scripts.backfill_indexacao.indexar_chave", return_value=("sucesso", None),
    )
    checkpoint = _checkpoint()
    marcar_processado(checkpoint, CHAVES[0], "sucesso")

    backfill_indexacao(
        CHAVES, mocker.MagicMock(), "https://api.example", "tok", checkpoint, pausa=0,
    )

    assert indexar.call_count == 1


def test_backfill_indexacao_dry_run_nao_baixa_nem_posta(mocker):
    indexar = mocker.patch("scripts.backfill_indexacao.indexar_chave")
    r2 = mocker.MagicMock()
    checkpoint = _checkpoint()

    backfill_indexacao(
        CHAVES, r2, "https://api.example", "tok", checkpoint, pausa=0, dry_run=True,
    )

    indexar.assert_not_called()
    r2.download_bytes.assert_not_called()
    assert {i["status"] for i in checkpoint.itens} == {"pulado_dedupe"}


def test_cli_dry_run_lista_do_r2_e_sai_zero(tmp_path, mocker, monkeypatch):
    monkeypatch.chdir(tmp_path)  # sem .env no cwd
    r2 = mocker.MagicMock()
    r2.listar.return_value = CHAVES
    mocker.patch(
        "scripts.backfill_indexacao.R2Client.from_env", return_value=r2,
    )

    codigo = main(["--dry-run", "--checkpoint-dir", str(tmp_path / "ckpt")])

    assert codigo == 0
    r2.listar.assert_called_once_with("texto/")
    persistido = carregar_checkpoint(tmp_path / "ckpt" / "indexacao.json")
    assert len(persistido.itens) == 2


def test_cli_sem_env_vars_falha_sem_dry_run(tmp_path, mocker, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEARCH_API_URL", raising=False)
    monkeypatch.delenv("SEARCH_API_TOKEN", raising=False)
    mocker.patch(
        "scripts.backfill_indexacao.R2Client.from_env",
        return_value=mocker.MagicMock(),
    )

    codigo = main(["--checkpoint-dir", str(tmp_path / "ckpt")])

    assert codigo == 2
