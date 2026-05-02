"""Testes de orquestração do coletor (fase RED — funções ainda não existem)."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from scripts.config import Fonte
from scripts.coletar import (
    main,
    processar_descoberta,
    processar_fonte,
)


def _fonte_mprr() -> Fonte:
    return Fonte(codigo="mprr", nome="MPRR", discovery_module="mprr")


def _descoberta_completa() -> dict:
    return {
        "url": "https://mprr.mp.br/x.pdf",
        "data_edicao": "2026-04-30",
        "numero": 951,
        "titulo": "Diário Eletrônico do MPRR n. 951-2026",
    }


def _extract_metadados_kwarg(call) -> dict:
    """Extrai o argumento `metadados` (kwarg ou 3º posicional) de uma chamada."""
    if "metadados" in call.kwargs:
        return call.kwargs["metadados"]
    if len(call.args) >= 3:
        return call.args[2]
    raise AssertionError("metadados não encontrado na chamada")


# --------------------------------------------------------------------------
# GRUPO A — processar_descoberta
# --------------------------------------------------------------------------

def test_processar_descoberta_pula_download_se_ja_existe_no_r2(mocker):
    r2 = MagicMock()
    r2.existe.return_value = True
    r2.url_publica.return_value = "https://pub-xxx/ja-existe"

    baixar = mocker.patch("scripts.coletar.baixar_pdf")
    mocker.patch("scripts.coletar.gravar_metadados", return_value=Path("/tmp/x.json"))

    result = processar_descoberta(_fonte_mprr(), _descoberta_completa(), r2)

    baixar.assert_not_called()
    r2.upload.assert_not_called()
    assert result is not None
    assert result["ja_existia"] is True


def test_processar_descoberta_baixa_e_sobe_quando_nao_existe(mocker):
    r2 = MagicMock()
    r2.existe.return_value = False
    r2.upload.return_value = "https://pub-xxx/url-publica"

    mocker.patch("scripts.coletar.baixar_pdf", return_value=("hash-abc", 12345))
    mocker.patch(
        "scripts.coletar.submeter_wayback",
        return_value="https://wayback/snapshot",
    )
    mocker.patch("scripts.coletar.gravar_metadados", return_value=Path("/tmp/x.json"))

    result = processar_descoberta(_fonte_mprr(), _descoberta_completa(), r2)

    assert result is not None
    chaves_esperadas = {
        "orgao", "data_edicao", "numero", "sha256", "tamanho",
        "url_original", "url_r2", "url_wayback", "ja_existia",
    }
    assert chaves_esperadas.issubset(result.keys())
    assert result["ja_existia"] is False
    assert result["sha256"] == "hash-abc"
    assert result["tamanho"] == 12345
    assert result["url_r2"] == "https://pub-xxx/url-publica"
    assert result["url_wayback"] == "https://wayback/snapshot"
    assert result["url_original"] == "https://mprr.mp.br/x.pdf"
    assert result["data_edicao"] == "2026-04-30"
    assert result["numero"] == 951
    assert result["orgao"] == "mprr"


def test_processar_descoberta_passa_metadados_pro_r2_upload(mocker):
    r2 = MagicMock()
    r2.existe.return_value = False
    r2.upload.return_value = "https://pub-xxx/x.pdf"

    mocker.patch("scripts.coletar.baixar_pdf", return_value=("hash-abc", 12345))
    mocker.patch("scripts.coletar.submeter_wayback", return_value=None)
    mocker.patch("scripts.coletar.gravar_metadados", return_value=Path("/tmp/x.json"))

    processar_descoberta(_fonte_mprr(), _descoberta_completa(), r2)

    metadados = _extract_metadados_kwarg(r2.upload.call_args)
    assert metadados["sha256"] == "hash-abc"
    assert metadados["data-edicao"] == "2026-04-30"


def test_processar_descoberta_continua_se_wayback_falhar(mocker):
    r2 = MagicMock()
    r2.existe.return_value = False
    r2.upload.return_value = "https://pub-xxx/x.pdf"

    mocker.patch("scripts.coletar.baixar_pdf", return_value=("hash-abc", 12345))
    mocker.patch("scripts.coletar.submeter_wayback", return_value=None)
    mocker.patch("scripts.coletar.gravar_metadados", return_value=Path("/tmp/x.json"))

    result = processar_descoberta(_fonte_mprr(), _descoberta_completa(), r2)

    assert result is not None
    assert result["url_wayback"] is None


def test_processar_descoberta_retorna_none_se_baixar_falhar(mocker):
    r2 = MagicMock()
    r2.existe.return_value = False

    mocker.patch(
        "scripts.coletar.baixar_pdf",
        side_effect=requests.RequestException("rede caiu"),
    )
    gravar = mocker.patch("scripts.coletar.gravar_metadados")

    result = processar_descoberta(_fonte_mprr(), _descoberta_completa(), r2)

    assert result is None
    r2.upload.assert_not_called()
    gravar.assert_not_called()


def test_processar_descoberta_propaga_erro_de_upload_r2(mocker):
    r2 = MagicMock()
    r2.existe.return_value = False
    r2.upload.side_effect = RuntimeError("R2 falhou feio")

    mocker.patch("scripts.coletar.baixar_pdf", return_value=("hash-abc", 12345))
    mocker.patch("scripts.coletar.submeter_wayback", return_value=None)
    mocker.patch("scripts.coletar.gravar_metadados", return_value=Path("/tmp/x.json"))

    with pytest.raises(RuntimeError, match="R2 falhou feio"):
        processar_descoberta(_fonte_mprr(), _descoberta_completa(), r2)


# --------------------------------------------------------------------------
# GRUPO B — processar_fonte
# --------------------------------------------------------------------------

def test_processar_fonte_chama_discover_e_delega(mocker):
    descoberta = _descoberta_completa()
    mod_mock = MagicMock()
    mod_mock.discover.return_value = descoberta

    # Ordem importa: importlib é patchado por último; ver mock docs.
    proc_desc = mocker.patch(
        "scripts.coletar.processar_descoberta",
        return_value={"orgao": "mprr"},
    )
    mocker.patch("scripts.coletar.importlib.import_module", return_value=mod_mock)

    r2 = MagicMock()
    processar_fonte(_fonte_mprr(), date(2026, 4, 30), r2)

    mod_mock.discover.assert_called_once_with(date(2026, 4, 30))
    proc_desc.assert_called_once()
    # descoberta deve ter sido passada (posicional ou kwarg)
    call = proc_desc.call_args
    if "descoberta" in call.kwargs:
        assert call.kwargs["descoberta"] == descoberta
    else:
        assert descoberta in call.args


def test_processar_fonte_retorna_none_se_discover_devolve_none(mocker):
    mod_mock = MagicMock()
    mod_mock.discover.return_value = None

    mocker.patch("scripts.coletar.importlib.import_module", return_value=mod_mock)
    proc_desc = mocker.patch("scripts.coletar.processar_descoberta")

    result = processar_fonte(_fonte_mprr(), date(2026, 4, 30), MagicMock())

    assert result is None
    proc_desc.assert_not_called()


# --------------------------------------------------------------------------
# GRUPO C — main (entry point)
# --------------------------------------------------------------------------

def _data_passada_em(call):
    """Devolve o data_alvo passado a processar_fonte (posicional ou kwarg)."""
    if "data_alvo" in call.kwargs:
        return call.kwargs["data_alvo"]
    return call.args[1]


def test_main_aceita_data_hoje(mocker):
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())
    proc_fonte = mocker.patch(
        "scripts.coletar.processar_fonte",
        return_value={"ja_existia": False},
    )

    main(["--data", "hoje", "--fonte", "tjrr"])

    proc_fonte.assert_called_once()
    assert _data_passada_em(proc_fonte.call_args) == date.today()


def test_main_aceita_data_ontem(mocker):
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())
    proc_fonte = mocker.patch(
        "scripts.coletar.processar_fonte",
        return_value={"ja_existia": False},
    )

    main(["--data", "ontem", "--fonte", "tjrr"])

    assert _data_passada_em(proc_fonte.call_args) == date.today() - timedelta(days=1)


def test_main_aceita_data_iso(mocker):
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())
    proc_fonte = mocker.patch(
        "scripts.coletar.processar_fonte",
        return_value={"ja_existia": False},
    )

    main(["--data", "2026-04-30", "--fonte", "tjrr"])

    assert _data_passada_em(proc_fonte.call_args) == date(2026, 4, 30)


def test_main_levanta_se_data_invalida(mocker):
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())
    mocker.patch("scripts.coletar.processar_fonte", return_value={"ja_existia": False})

    with pytest.raises(SystemExit):
        main(["--data", "2026/04/30", "--fonte", "tjrr"])


def test_main_fonte_todas_processa_todas_as_fontes(mocker):
    fontes_mock = [
        Fonte(codigo="mprr", nome="MPRR", discovery_module="mprr"),
        Fonte(codigo="tjrr", nome="TJRR", discovery_module="tjrr"),
    ]
    mocker.patch("scripts.coletar.FONTES", fontes_mock)
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())
    proc_fonte = mocker.patch(
        "scripts.coletar.processar_fonte",
        return_value={"ja_existia": False},
    )

    main(["--data", "hoje", "--fonte", "todas"])

    assert proc_fonte.call_count == 2
    codigos = [c.args[0].codigo for c in proc_fonte.call_args_list]
    assert set(codigos) == {"mprr", "tjrr"}


def test_main_fonte_invalida_levanta_systemexit(mocker):
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())
    mocker.patch("scripts.coletar.processar_fonte", return_value={"ja_existia": False})

    with pytest.raises(SystemExit):
        main(["--data", "hoje", "--fonte", "inexistente"])


def test_main_retorna_zero_em_sucesso(mocker):
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())
    mocker.patch(
        "scripts.coletar.processar_fonte",
        return_value={"ja_existia": False},
    )

    rc = main(["--data", "hoje", "--fonte", "tjrr"])

    assert rc == 0


def test_main_retorna_um_se_houve_erro(mocker):
    fontes_mock = [
        Fonte(codigo="mprr", nome="MPRR", discovery_module="mprr"),
        Fonte(codigo="tjrr", nome="TJRR", discovery_module="tjrr"),
    ]
    mocker.patch("scripts.coletar.FONTES", fontes_mock)
    mocker.patch("scripts.coletar.R2Client.from_env", return_value=MagicMock())

    chamadas: list[str] = []

    def side_effect(fonte, data_alvo, r2):
        chamadas.append(fonte.codigo)
        if fonte.codigo == "mprr":
            raise RuntimeError("falha em mprr")
        return {"ja_existia": False}

    mocker.patch("scripts.coletar.processar_fonte", side_effect=side_effect)

    rc = main(["--data", "hoje", "--fonte", "todas"])

    assert rc == 1
    assert chamadas == ["mprr", "tjrr"]
