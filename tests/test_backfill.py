"""Testes do scripts.backfill — núcleo (fase RED — implementação ainda não existe)."""

import json
from datetime import date, datetime

import pytest

from scripts.backfill import (
    Checkpoint,
    carregar_checkpoint,
    gerar_datas,
    gravar_checkpoint,
    ja_processado,
    marcar_processado,
)


def _empty_cp() -> Checkpoint:
    return Checkpoint(
        escopo="teste",
        iniciado_em="2026-05-03T20:00:00",
        atualizado_em="2026-05-03T20:00:00",
        itens=[],
        config={},
    )


# --------------------------------------------------------------------------
# GRUPO A — gerar_datas
# --------------------------------------------------------------------------

def test_gerar_datas_intervalo_simples():
    datas = gerar_datas(date(2026, 4, 28), date(2026, 4, 30))

    assert datas == [date(2026, 4, 28), date(2026, 4, 29), date(2026, 4, 30)]


def test_gerar_datas_data_unica():
    assert gerar_datas(date(2026, 4, 30), date(2026, 4, 30)) == [date(2026, 4, 30)]


def test_gerar_datas_somente_uteis_pula_fim_de_semana():
    # Maio 2026: 1 = sex, 2 = sáb, 3 = dom, 4 = seg
    datas = gerar_datas(date(2026, 5, 1), date(2026, 5, 4), somente_uteis=True)

    assert datas == [date(2026, 5, 1), date(2026, 5, 4)]


def test_gerar_datas_levanta_se_de_maior_que_ate():
    with pytest.raises(ValueError):
        gerar_datas(date(2026, 5, 10), date(2026, 5, 5))


def test_gerar_datas_intervalo_de_um_ano_completo():
    datas = gerar_datas(date(2026, 1, 1), date(2026, 12, 31))

    assert len(datas) == 365


def test_gerar_datas_somente_uteis_intervalo_grande():
    datas = gerar_datas(date(2026, 1, 1), date(2026, 12, 31), somente_uteis=True)

    assert len(datas) == 261


# --------------------------------------------------------------------------
# GRUPO B — Checkpoint (dataclass mutável)
# --------------------------------------------------------------------------

def test_checkpoint_aceita_atributos_obrigatorios():
    cp = Checkpoint(
        escopo="mprr-2022",
        iniciado_em="2026-05-03T20:00:00",
        atualizado_em="2026-05-03T20:00:00",
        itens=[],
        config={"fonte": "mprr", "anos": [2022]},
    )

    assert cp.escopo == "mprr-2022"
    assert cp.itens == []
    assert cp.config == {"fonte": "mprr", "anos": [2022]}


def test_checkpoint_e_mutavel():
    cp = _empty_cp()
    cp.itens.append({
        "id": "x",
        "status": "sucesso",
        "detalhes": None,
        "timestamp": "2026-05-03T20:01:00",
    })

    assert len(cp.itens) == 1


# --------------------------------------------------------------------------
# GRUPO C — gravar_checkpoint e carregar_checkpoint
# --------------------------------------------------------------------------

def test_gravar_e_carregar_round_trip(tmp_path):
    cp = Checkpoint(
        escopo="mprr-2022",
        iniciado_em="2026-05-03T20:00:00",
        atualizado_em="2026-05-03T20:00:00",
        itens=[
            {"id": "a", "status": "sucesso", "detalhes": None,
             "timestamp": "2026-05-03T20:01:00"},
            {"id": "b", "status": "erro", "detalhes": "rede caiu",
             "timestamp": "2026-05-03T20:02:00"},
        ],
        config={"fonte": "mprr", "anos": [2022]},
    )

    caminho = tmp_path / "ck.json"
    gravar_checkpoint(cp, caminho)
    carregado = carregar_checkpoint(caminho)

    assert carregado is not None
    assert carregado.escopo == cp.escopo
    assert carregado.itens == cp.itens
    assert carregado.config == cp.config


def test_carregar_checkpoint_retorna_none_se_arquivo_nao_existe(tmp_path):
    assert carregar_checkpoint(tmp_path / "nao_existe.json") is None


def test_carregar_checkpoint_levanta_se_json_invalido(tmp_path):
    caminho = tmp_path / "corrompido.json"
    caminho.write_text("{ corrupt", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        carregar_checkpoint(caminho)


def test_gravar_checkpoint_cria_diretorio_pai(tmp_path):
    caminho = tmp_path / "data" / "backfill" / "ck.json"
    cp = _empty_cp()

    gravar_checkpoint(cp, caminho)

    assert caminho.exists()


def test_gravar_checkpoint_atualiza_timestamp_antes_de_gravar(mocker, tmp_path):
    fake_now = mocker.MagicMock()
    fake_now.isoformat.return_value = "2026-05-03T22:00:00"
    fake_dt = mocker.patch("scripts.backfill.datetime")
    fake_dt.now.return_value = fake_now

    cp = Checkpoint(
        escopo="x",
        iniciado_em="2026-05-03T20:00:00",
        atualizado_em="antigo",
        itens=[],
        config={},
    )
    caminho = tmp_path / "ck.json"
    gravar_checkpoint(cp, caminho)

    assert cp.atualizado_em == "2026-05-03T22:00:00"
    raw = caminho.read_text(encoding="utf-8")
    assert "2026-05-03T22:00:00" in raw


def test_gravar_checkpoint_serializa_com_indent_e_utf8(tmp_path):
    cp = Checkpoint(
        escopo="x",
        iniciado_em="2026-05-03T20:00:00",
        atualizado_em="2026-05-03T20:00:00",
        itens=[],
        config={"descricao": "teste com çãõ unicode"},
    )

    caminho = tmp_path / "ck.json"
    gravar_checkpoint(cp, caminho)

    raw = caminho.read_text(encoding="utf-8")
    assert "\n  " in raw
    assert "\\u" not in raw


# --------------------------------------------------------------------------
# GRUPO D — marcar_processado e ja_processado
# --------------------------------------------------------------------------

def test_marcar_processado_adiciona_item_com_timestamp():
    cp = _empty_cp()

    marcar_processado(cp, "edicao-951", "sucesso")

    assert len(cp.itens) == 1
    item = cp.itens[0]
    assert item["id"] == "edicao-951"
    assert item["status"] == "sucesso"
    assert item["detalhes"] is None
    assert "timestamp" in item
    # timestamp deve ser um ISO datetime parseável
    datetime.fromisoformat(item["timestamp"])


def test_marcar_processado_aceita_detalhes_opcionais():
    cp = _empty_cp()

    marcar_processado(cp, "edicao-x", "erro", detalhes="HTTPError 500")

    assert cp.itens[0]["detalhes"] == "HTTPError 500"


@pytest.mark.parametrize("status", ["ok", "fail", "skipped", "completed"])
def test_marcar_processado_status_invalido_levanta(status):
    cp = _empty_cp()

    with pytest.raises(ValueError) as exc:
        marcar_processado(cp, "id", status)

    assert status in str(exc.value)


@pytest.mark.parametrize(
    "status", ["sucesso", "erro", "pulado_dedupe", "sem_diario"]
)
def test_marcar_processado_aceita_4_status_validos(status):
    cp = _empty_cp()

    marcar_processado(cp, "id", status)

    assert cp.itens[0]["status"] == status


def test_ja_processado_retorna_true_para_id_existente():
    cp = _empty_cp()
    cp.itens = [
        {"id": "a", "status": "sucesso", "detalhes": None,
         "timestamp": "2026-05-03T20:00:00"},
        {"id": "b", "status": "erro", "detalhes": "x",
         "timestamp": "2026-05-03T20:01:00"},
    ]

    assert ja_processado(cp, "a") is True
    assert ja_processado(cp, "b") is True


def test_ja_processado_retorna_false_para_id_inexistente():
    cp = _empty_cp()
    cp.itens = [
        {"id": "a", "status": "sucesso", "detalhes": None,
         "timestamp": "2026-05-03T20:00:00"},
        {"id": "b", "status": "erro", "detalhes": "x",
         "timestamp": "2026-05-03T20:01:00"},
    ]

    assert ja_processado(cp, "c") is False


def test_ja_processado_em_checkpoint_vazio_retorna_false():
    cp = _empty_cp()

    assert ja_processado(cp, "qualquer") is False
