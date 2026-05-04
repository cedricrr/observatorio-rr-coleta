"""Testes de orquestração do backfill (fase RED — funções ainda não existem)."""

from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from scripts.config import Fonte
from scripts.backfill import (
    Checkpoint,
    backfill_daily,
    backfill_listing,
    gerar_relatorio,
    main,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _mprr_fonte() -> Fonte:
    return Fonte(codigo="mprr", nome="MPRR", discovery_module="mprr")


def _tjrr_fonte() -> Fonte:
    return Fonte(codigo="tjrr", nome="TJRR", discovery_module="tjrr")


def _empty_checkpoint(escopo: str = "teste") -> Checkpoint:
    return Checkpoint(
        escopo=escopo,
        iniciado_em="2026-05-03T20:00:00",
        atualizado_em="2026-05-03T20:00:00",
        itens=[],
        config={},
    )


def _descoberta(numero: int, data: str) -> dict:
    return {
        "url": f"https://mprr.mp.br/{numero}.pdf",
        "data_edicao": data,
        "numero": numero,
        "titulo": f"Edição {numero}",
    }


# --------------------------------------------------------------------------
# GRUPO A — backfill_listing (modo MPRR)
# --------------------------------------------------------------------------

def test_listing_processa_todas_edicoes_de_todos_anos(mocker):
    # Ordem: processar_descoberta primeiro, importlib por último
    # (ver feedback_mock_patch_importlib_ordem)
    proc = mocker.patch(
        "scripts.backfill.processar_descoberta",
        return_value={"ja_existia": False},
    )
    mocker.patch("scripts.backfill.time.sleep")

    mod_mock = MagicMock()

    def fake_list_year(ano):
        return {
            2024: [_descoberta(800, "2024-06-01"), _descoberta(801, "2024-06-02")],
            2025: [_descoberta(900, "2025-06-01")],
        }[ano]

    mod_mock.list_year.side_effect = fake_list_year
    mocker.patch("scripts.backfill.importlib.import_module", return_value=mod_mock)

    cp = _empty_checkpoint()
    backfill_listing(_mprr_fonte(), [2024, 2025], MagicMock(), cp, pausa=0)

    assert proc.call_count == 3
    assert len(cp.itens) == 3
    assert all(item["status"] == "sucesso" for item in cp.itens)


def test_listing_pula_itens_ja_processados(mocker):
    proc = mocker.patch(
        "scripts.backfill.processar_descoberta",
        return_value={"ja_existia": False},
    )
    mocker.patch("scripts.backfill.time.sleep")

    mod_mock = MagicMock()
    mod_mock.list_year.return_value = [
        _descoberta(800, "2024-06-01"),
        _descoberta(801, "2024-06-02"),
    ]
    mocker.patch("scripts.backfill.importlib.import_module", return_value=mod_mock)

    cp = _empty_checkpoint()
    cp.itens.append({
        "id": "mprr-2024-06-01-800",
        "status": "sucesso",
        "detalhes": None,
        "timestamp": "2026-05-01T00:00:00",
    })

    backfill_listing(_mprr_fonte(), [2024], MagicMock(), cp, pausa=0)

    assert proc.call_count == 1
    assert len(cp.itens) == 2


def test_listing_marca_erro_em_falha_de_processar_descoberta(mocker):
    mocker.patch(
        "scripts.backfill.processar_descoberta",
        side_effect=requests.RequestException("fail"),
    )
    mocker.patch("scripts.backfill.time.sleep")

    mod_mock = MagicMock()
    mod_mock.list_year.return_value = [_descoberta(800, "2024-06-01")]
    mocker.patch("scripts.backfill.importlib.import_module", return_value=mod_mock)

    cp = _empty_checkpoint()
    backfill_listing(_mprr_fonte(), [2024], MagicMock(), cp, pausa=0)

    assert len(cp.itens) == 1
    assert cp.itens[0]["status"] == "erro"
    assert "fail" in cp.itens[0]["detalhes"]


def test_listing_continua_apos_erro_em_um_item(mocker):
    mocker.patch(
        "scripts.backfill.processar_descoberta",
        side_effect=[
            {"ja_existia": False},
            requests.RequestException("falha 2"),
            {"ja_existia": False},
        ],
    )
    mocker.patch("scripts.backfill.time.sleep")

    mod_mock = MagicMock()
    mod_mock.list_year.return_value = [
        _descoberta(800, "2024-06-01"),
        _descoberta(801, "2024-06-02"),
        _descoberta(802, "2024-06-03"),
    ]
    mocker.patch("scripts.backfill.importlib.import_module", return_value=mod_mock)

    cp = _empty_checkpoint()
    backfill_listing(_mprr_fonte(), [2024], MagicMock(), cp, pausa=0)

    statuses = [item["status"] for item in cp.itens]
    assert statuses == ["sucesso", "erro", "sucesso"]


def test_listing_aplica_pausa_entre_itens(mocker):
    mocker.patch(
        "scripts.backfill.processar_descoberta",
        return_value={"ja_existia": False},
    )
    sleep = mocker.patch("scripts.backfill.time.sleep")

    mod_mock = MagicMock()
    mod_mock.list_year.return_value = [
        _descoberta(800, "2024-06-01"),
        _descoberta(801, "2024-06-02"),
        _descoberta(802, "2024-06-03"),
    ]
    mocker.patch("scripts.backfill.importlib.import_module", return_value=mod_mock)

    cp = _empty_checkpoint()
    backfill_listing(_mprr_fonte(), [2024], MagicMock(), cp, pausa=2.5)

    assert sleep.call_count == 3
    for call in sleep.call_args_list:
        assert call.args[0] == 2.5


def test_listing_pausa_zero_nao_chama_sleep(mocker):
    mocker.patch(
        "scripts.backfill.processar_descoberta",
        return_value={"ja_existia": False},
    )
    sleep = mocker.patch("scripts.backfill.time.sleep")

    mod_mock = MagicMock()
    mod_mock.list_year.return_value = [
        _descoberta(800, "2024-06-01"),
        _descoberta(801, "2024-06-02"),
        _descoberta(802, "2024-06-03"),
    ]
    mocker.patch("scripts.backfill.importlib.import_module", return_value=mod_mock)

    cp = _empty_checkpoint()
    backfill_listing(_mprr_fonte(), [2024], MagicMock(), cp, pausa=0)

    sleep.assert_not_called()


def test_listing_em_dry_run_nao_chama_processar_descoberta(mocker):
    """Em dry-run, backfill_listing não baixa nem processa — apenas
    registra o que seria feito."""
    proc = mocker.patch("scripts.backfill.processar_descoberta")
    mocker.patch("scripts.backfill.time.sleep")

    mod_mock = MagicMock()
    mod_mock.list_year.return_value = [
        _descoberta(800, "2024-06-01"),
        _descoberta(801, "2024-06-02"),
    ]
    mocker.patch("scripts.backfill.importlib.import_module", return_value=mod_mock)

    cp = _empty_checkpoint()
    backfill_listing(
        _mprr_fonte(), [2024], r2=None, checkpoint=cp, pausa=0,
        dry_run=True,
    )

    proc.assert_not_called()
    # itens são registrados como "pulado_dedupe" para indicar simulação
    # (escolha de design: dry-run não distorce contagem de "sucesso")
    assert len(cp.itens) == 2
    assert all(item["status"] == "pulado_dedupe" for item in cp.itens)


# --------------------------------------------------------------------------
# GRUPO B — backfill_daily (modo TJRR)
# --------------------------------------------------------------------------

def test_daily_processa_todas_datas_do_intervalo(mocker):
    proc = mocker.patch(
        "scripts.backfill.processar_fonte",
        return_value={"ja_existia": False},
    )
    mocker.patch("scripts.backfill.time.sleep")

    cp = _empty_checkpoint()
    backfill_daily(
        _tjrr_fonte(),
        date(2026, 4, 28),
        date(2026, 4, 30),
        somente_uteis=False,
        r2=MagicMock(),
        checkpoint=cp,
        pausa=0,
    )

    assert proc.call_count == 3
    assert len(cp.itens) == 3
    assert all(item["status"] == "sucesso" for item in cp.itens)


def test_daily_pula_fim_de_semana_se_solicitado(mocker):
    proc = mocker.patch(
        "scripts.backfill.processar_fonte",
        return_value={"ja_existia": False},
    )
    mocker.patch("scripts.backfill.time.sleep")

    cp = _empty_checkpoint()
    backfill_daily(
        _tjrr_fonte(),
        date(2026, 5, 1),
        date(2026, 5, 4),
        somente_uteis=True,
        r2=MagicMock(),
        checkpoint=cp,
        pausa=0,
    )

    assert proc.call_count == 2
    assert len(cp.itens) == 2


def test_daily_marca_sem_diario_se_processar_fonte_retorna_none(mocker):
    mocker.patch("scripts.backfill.processar_fonte", return_value=None)
    mocker.patch("scripts.backfill.time.sleep")

    cp = _empty_checkpoint()
    backfill_daily(
        _tjrr_fonte(),
        date(2026, 4, 30),
        date(2026, 4, 30),
        somente_uteis=False,
        r2=MagicMock(),
        checkpoint=cp,
        pausa=0,
    )

    assert cp.itens[0]["status"] == "sem_diario"


def test_daily_marca_erro_em_excecao(mocker):
    mocker.patch(
        "scripts.backfill.processar_fonte",
        side_effect=RuntimeError("explodiu"),
    )
    mocker.patch("scripts.backfill.time.sleep")

    cp = _empty_checkpoint()
    backfill_daily(
        _tjrr_fonte(),
        date(2026, 4, 30),
        date(2026, 4, 30),
        somente_uteis=False,
        r2=MagicMock(),
        checkpoint=cp,
        pausa=0,
    )

    assert cp.itens[0]["status"] == "erro"
    assert "explodiu" in cp.itens[0]["detalhes"]


def test_daily_aplica_pausa_entre_datas(mocker):
    mocker.patch(
        "scripts.backfill.processar_fonte",
        return_value={"ja_existia": False},
    )
    sleep = mocker.patch("scripts.backfill.time.sleep")

    cp = _empty_checkpoint()
    backfill_daily(
        _tjrr_fonte(),
        date(2026, 4, 28),
        date(2026, 4, 30),
        somente_uteis=False,
        r2=MagicMock(),
        checkpoint=cp,
        pausa=1.5,
    )

    assert sleep.call_count == 3
    for call in sleep.call_args_list:
        assert call.args[0] == 1.5


def test_daily_pula_datas_ja_processadas(mocker):
    proc = mocker.patch(
        "scripts.backfill.processar_fonte",
        return_value={"ja_existia": False},
    )
    mocker.patch("scripts.backfill.time.sleep")

    cp = _empty_checkpoint()
    cp.itens.append({
        "id": "tjrr-2026-04-28",
        "status": "sucesso",
        "detalhes": None,
        "timestamp": "2026-05-01T00:00:00",
    })

    backfill_daily(
        _tjrr_fonte(),
        date(2026, 4, 28),
        date(2026, 4, 30),
        somente_uteis=False,
        r2=MagicMock(),
        checkpoint=cp,
        pausa=0,
    )

    assert proc.call_count == 2


# --------------------------------------------------------------------------
# GRUPO C — gerar_relatorio
# --------------------------------------------------------------------------

def test_relatorio_conta_itens_por_status():
    cp = _empty_checkpoint("mprr-2024")
    cp.itens = [
        {"id": "1", "status": "sucesso", "detalhes": None, "timestamp": "..."},
        {"id": "2", "status": "sucesso", "detalhes": None, "timestamp": "..."},
        {"id": "3", "status": "sucesso", "detalhes": None, "timestamp": "..."},
        {"id": "4", "status": "erro", "detalhes": "x", "timestamp": "..."},
        {"id": "5", "status": "sem_diario", "detalhes": None, "timestamp": "..."},
    ]

    rel = gerar_relatorio(cp).lower()

    assert "sucesso: 3" in rel
    assert "erro: 1" in rel
    assert "sem_diario: 1" in rel
    assert "total: 5" in rel


def test_relatorio_inclui_escopo():
    cp = _empty_checkpoint("mprr-2024-2025")

    assert "mprr-2024-2025" in gerar_relatorio(cp)


def test_relatorio_em_checkpoint_vazio():
    cp = _empty_checkpoint()

    rel = gerar_relatorio(cp).lower()

    assert "total: 0" in rel


# --------------------------------------------------------------------------
# GRUPO D — main (CLI)
# --------------------------------------------------------------------------

def _mock_main_essentials(mocker):
    """Mocks essenciais para todos os testes de main."""
    mocker.patch("scripts.backfill.R2Client.from_env", return_value=MagicMock())
    mocker.patch("scripts.backfill.time.sleep")
    mocker.patch("scripts.backfill.gravar_checkpoint")


def test_main_modo_listing_chama_backfill_listing(mocker):
    _mock_main_essentials(mocker)
    backfill_l = mocker.patch(
        "scripts.backfill.backfill_listing",
        return_value=_empty_checkpoint(),
    )

    main(["--fonte", "mprr", "--anos", "2024,2025"])

    backfill_l.assert_called_once()
    fonte_arg = backfill_l.call_args.args[0]
    anos_arg = backfill_l.call_args.args[1]
    assert fonte_arg.codigo == "mprr"
    assert anos_arg == [2024, 2025]


def test_main_modo_daily_chama_backfill_daily(mocker):
    _mock_main_essentials(mocker)
    backfill_d = mocker.patch(
        "scripts.backfill.backfill_daily",
        return_value=_empty_checkpoint(),
    )

    main(["--fonte", "tjrr", "--de", "2026-04-01", "--ate", "2026-04-30"])

    backfill_d.assert_called_once()
    args = backfill_d.call_args.args
    assert args[0].codigo == "tjrr"
    assert args[1] == date(2026, 4, 1)
    assert args[2] == date(2026, 4, 30)


def test_main_anos_e_intervalo_sao_mutuamente_exclusivos(mocker):
    _mock_main_essentials(mocker)
    mocker.patch("scripts.backfill.backfill_listing", return_value=_empty_checkpoint())
    mocker.patch("scripts.backfill.backfill_daily", return_value=_empty_checkpoint())

    with pytest.raises(SystemExit):
        main([
            "--fonte", "mprr",
            "--anos", "2024",
            "--de", "2026-01-01",
            "--ate", "2026-12-31",
        ])


def test_main_de_sem_ate_levanta(mocker):
    _mock_main_essentials(mocker)
    mocker.patch("scripts.backfill.backfill_daily", return_value=_empty_checkpoint())

    with pytest.raises(SystemExit):
        main(["--fonte", "tjrr", "--de", "2026-01-01"])


def test_main_anos_invalido_levanta(mocker):
    _mock_main_essentials(mocker)
    mocker.patch("scripts.backfill.backfill_listing", return_value=_empty_checkpoint())

    with pytest.raises((SystemExit, ValueError)):
        main(["--fonte", "mprr", "--anos", "2024,abc,2025"])


def test_main_pausa_padrao_eh_3(mocker):
    _mock_main_essentials(mocker)
    backfill_l = mocker.patch(
        "scripts.backfill.backfill_listing",
        return_value=_empty_checkpoint(),
    )

    main(["--fonte", "mprr", "--anos", "2024"])

    call = backfill_l.call_args
    pausa = call.kwargs.get("pausa")
    if pausa is None:
        pausa = call.args[4]
    assert pausa == 3.0


def test_main_pausa_customizada(mocker):
    _mock_main_essentials(mocker)
    backfill_l = mocker.patch(
        "scripts.backfill.backfill_listing",
        return_value=_empty_checkpoint(),
    )

    main(["--fonte", "mprr", "--anos", "2024", "--pausa", "5"])

    call = backfill_l.call_args
    pausa = call.kwargs.get("pausa")
    if pausa is None:
        pausa = call.args[4]
    assert pausa == 5.0


def test_main_dry_run_nao_chama_r2(mocker):
    from_env = mocker.patch("scripts.backfill.R2Client.from_env", return_value=MagicMock())
    mocker.patch("scripts.backfill.time.sleep")
    mocker.patch("scripts.backfill.gravar_checkpoint")
    backfill_l = mocker.patch(
        "scripts.backfill.backfill_listing",
        return_value=_empty_checkpoint(),
    )

    main(["--fonte", "mprr", "--anos", "2024", "--dry-run"])

    from_env.assert_not_called()
    backfill_l.assert_called_once()


def test_main_retomar_carrega_checkpoint_existente(mocker):
    _mock_main_essentials(mocker)

    cp_existente = Checkpoint(
        escopo="mprr-2024",
        iniciado_em="2026-05-01T00:00:00",
        atualizado_em="2026-05-01T01:00:00",
        itens=[{
            "id": "x",
            "status": "sucesso",
            "detalhes": None,
            "timestamp": "2026-05-01T00:30:00",
        }],
        config={},
    )
    mocker.patch("scripts.backfill.carregar_checkpoint", return_value=cp_existente)
    backfill_l = mocker.patch(
        "scripts.backfill.backfill_listing",
        return_value=cp_existente,
    )

    main(["--fonte", "mprr", "--anos", "2024", "--retomar"])

    cp_passed = backfill_l.call_args.args[3]
    assert cp_passed.itens == cp_existente.itens


def test_main_grava_checkpoint_apos_execucao(mocker):
    mocker.patch("scripts.backfill.R2Client.from_env", return_value=MagicMock())
    mocker.patch("scripts.backfill.time.sleep")
    grava = mocker.patch("scripts.backfill.gravar_checkpoint")

    cp = _empty_checkpoint()
    cp.itens = [{
        "id": "a", "status": "sucesso", "detalhes": None,
        "timestamp": "2026-05-03T20:00:00",
    }]
    mocker.patch("scripts.backfill.backfill_listing", return_value=cp)

    main(["--fonte", "mprr", "--anos", "2024"])

    assert grava.called


def test_main_imprime_relatorio_no_final(mocker, capsys):
    _mock_main_essentials(mocker)
    mocker.patch("scripts.backfill.backfill_listing", return_value=_empty_checkpoint())
    mocker.patch("scripts.backfill.gerar_relatorio", return_value="RELATORIO TESTE")

    main(["--fonte", "mprr", "--anos", "2024"])

    assert "RELATORIO TESTE" in capsys.readouterr().out


def test_main_retorna_0_em_sucesso(mocker):
    _mock_main_essentials(mocker)

    cp = _empty_checkpoint()
    cp.itens = [{
        "id": "a", "status": "sucesso", "detalhes": None,
        "timestamp": "2026-05-03T20:00:00",
    }]
    mocker.patch("scripts.backfill.backfill_listing", return_value=cp)

    rc = main(["--fonte", "mprr", "--anos", "2024"])

    assert rc == 0


def test_main_retorna_1_se_houver_erro(mocker):
    _mock_main_essentials(mocker)

    cp = _empty_checkpoint()
    cp.itens = [{
        "id": "a", "status": "erro", "detalhes": "x",
        "timestamp": "2026-05-03T20:00:00",
    }]
    mocker.patch("scripts.backfill.backfill_listing", return_value=cp)

    rc = main(["--fonte", "mprr", "--anos", "2024"])

    assert rc == 1
