"""Testes do scripts.indexar_diaria (indexação do dia no fluxo do Actions)."""

import json
from datetime import date
from pathlib import Path

from scripts.indexar_diaria import indexar_data, main, metadados_da_data


def _metadados(orgao: str, data_edicao: str, numero=None) -> dict:
    sufixo = f"-{numero}" if numero is not None else ""
    ano, mes, _ = data_edicao.split("-")
    return {
        "orgao": orgao,
        "data_edicao": data_edicao,
        "numero": numero,
        "sha256": "abc",
        "tamanho": 1000,
        "url_original": "https://example.com/x.pdf",
        "url_r2": (
            f"https://pub-xyz.r2.dev/{orgao}/{ano}/{mes}/{data_edicao}{sufixo}.pdf"
        ),
        "url_wayback": None,
        "ja_existia": False,
    }


def _criar_diarios_dir(tmp_path: Path) -> Path:
    diarios = tmp_path / "diarios"
    (diarios / "mprr").mkdir(parents=True)
    (diarios / "tjrr").mkdir(parents=True)
    for m, nome in [
        (_metadados("mprr", "2026-06-10", 977), "mprr/2026-06-10-977.json"),
        (_metadados("mprr", "2026-06-09", 976), "mprr/2026-06-09-976.json"),
        (_metadados("tjrr", "2026-06-10"), "tjrr/2026-06-10.json"),
    ]:
        (diarios / nome).write_text(json.dumps(m), encoding="utf-8")
    return diarios


def test_metadados_da_data_acha_todas_as_fontes(tmp_path):
    diarios = _criar_diarios_dir(tmp_path)

    lista = metadados_da_data(diarios, date(2026, 6, 10), ["mprr", "tjrr"])

    assert {(m["orgao"], m["numero"]) for m in lista} == {("mprr", 977), ("tjrr", None)}


def test_metadados_da_data_filtra_fonte(tmp_path):
    diarios = _criar_diarios_dir(tmp_path)

    lista = metadados_da_data(diarios, date(2026, 6, 10), ["tjrr"])

    assert len(lista) == 1
    assert lista[0]["orgao"] == "tjrr"


def test_metadados_da_data_sem_edicao_retorna_vazio(tmp_path):
    diarios = _criar_diarios_dir(tmp_path)

    assert metadados_da_data(diarios, date(2026, 6, 8), ["mprr", "tjrr"]) == []


def test_indexar_data_garante_cache_e_posta(tmp_path, mocker):
    diarios = _criar_diarios_dir(tmp_path)
    extrair = mocker.patch(
        "scripts.indexar_diaria.extrair_e_gravar",
        return_value=("pulado_dedupe", None),
    )
    indexar = mocker.patch(
        "scripts.indexar_diaria.indexar_chave",
        return_value=("sucesso", "29 paginas indexadas"),
    )
    r2 = mocker.MagicMock()

    indexadas, erros = indexar_data(
        date(2026, 6, 10), ["mprr", "tjrr"], diarios, r2, "https://api.example", "tok",
    )

    assert indexadas == 2
    assert erros == []
    assert extrair.call_count == 2
    chaves = [c.args[0] for c in indexar.call_args_list]
    assert "texto/mprr/2026/06/2026-06-10-977.json" in chaves
    assert "texto/tjrr/2026/06/2026-06-10.json" in chaves


def test_indexar_data_erro_em_uma_edicao_continua(tmp_path, mocker):
    diarios = _criar_diarios_dir(tmp_path)
    mocker.patch(
        "scripts.indexar_diaria.extrair_e_gravar",
        side_effect=[RuntimeError("PDF sumiu"), ("sucesso", None)],
    )
    mocker.patch(
        "scripts.indexar_diaria.indexar_chave", return_value=("sucesso", None),
    )

    indexadas, erros = indexar_data(
        date(2026, 6, 10), ["mprr", "tjrr"], diarios, mocker.MagicMock(),
        "https://api.example", "tok",
    )

    assert indexadas == 1
    assert len(erros) == 1
    assert "PDF sumiu" in erros[0]


def test_main_sem_edicao_na_data_sai_zero(tmp_path, mocker, monkeypatch):
    diarios = _criar_diarios_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_API_URL", "https://api.example")
    monkeypatch.setenv("SEARCH_API_TOKEN", "tok")
    mocker.patch(
        "scripts.indexar_diaria.R2Client.from_env", return_value=mocker.MagicMock(),
    )

    codigo = main(["--data", "2026-06-08", "--diarios-dir", str(diarios)])

    assert codigo == 0


def test_main_sucesso_sai_zero_e_erro_sai_um(tmp_path, mocker, monkeypatch):
    diarios = _criar_diarios_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_API_URL", "https://api.example")
    monkeypatch.setenv("SEARCH_API_TOKEN", "tok")
    mocker.patch(
        "scripts.indexar_diaria.R2Client.from_env", return_value=mocker.MagicMock(),
    )
    mocker.patch(
        "scripts.indexar_diaria.extrair_e_gravar", return_value=("sucesso", None),
    )
    indexar = mocker.patch(
        "scripts.indexar_diaria.indexar_chave", return_value=("sucesso", None),
    )

    assert main(["--data", "2026-06-10", "--diarios-dir", str(diarios)]) == 0

    indexar.side_effect = RuntimeError("api fora")
    assert main(["--data", "2026-06-10", "--diarios-dir", str(diarios)]) == 1


def test_main_aceita_data_ontem(tmp_path, mocker, monkeypatch):
    diarios = _criar_diarios_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEARCH_API_URL", "https://api.example")
    monkeypatch.setenv("SEARCH_API_TOKEN", "tok")
    mocker.patch(
        "scripts.indexar_diaria.R2Client.from_env", return_value=mocker.MagicMock(),
    )
    indexar_data = mocker.patch(
        "scripts.indexar_diaria.indexar_data", return_value=(0, []),
    )

    codigo = main(["--data", "ontem", "--diarios-dir", str(diarios)])

    assert codigo == 0
    from datetime import date as date_cls, timedelta

    assert indexar_data.call_args[0][0] == date_cls.today() - timedelta(days=1)


def test_main_sem_env_vars_sai_dois(tmp_path, monkeypatch, mocker):
    diarios = _criar_diarios_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEARCH_API_URL", raising=False)
    monkeypatch.delenv("SEARCH_API_TOKEN", raising=False)
    mocker.patch(
        "scripts.indexar_diaria.R2Client.from_env", return_value=mocker.MagicMock(),
    )

    assert main(["--data", "2026-06-10", "--diarios-dir", str(diarios)]) == 2
