"""Testes do wrapper de cliente Anthropic (Sub-ciclo 8.6b)."""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic  # noqa: F401 — referenciado em raises do teste 3
import pytest

from scripts.cliente_anthropic import ClienteAnthropic


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _criar_resposta_mock(texto: str):
    """Cria mock que simula resposta de anthropic.messages.create."""
    bloco_texto = MagicMock()
    bloco_texto.type = "text"
    bloco_texto.text = texto

    resposta = MagicMock()
    resposta.content = [bloco_texto]
    return resposta


# ---------------------------------------------------------------------------
# GRUPO A — Inicialização e autenticação
# ---------------------------------------------------------------------------

def test_init_com_api_key_explicita():
    cliente = ClienteAnthropic(api_key="sk-ant-test-key")
    assert cliente.model == ClienteAnthropic.DEFAULT_MODEL
    assert cliente.extended_thinking is True
    assert cliente.max_tokens == ClienteAnthropic.DEFAULT_MAX_TOKENS


def test_init_le_api_key_do_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
    cliente = ClienteAnthropic()
    assert cliente is not None
    assert cliente.model == ClienteAnthropic.DEFAULT_MODEL


def test_init_sem_key_em_lugar_nenhum_levanta_erro(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(
        (anthropic.AuthenticationError, ValueError, KeyError, Exception)
    ):
        ClienteAnthropic()


# ---------------------------------------------------------------------------
# GRUPO B — Configuração customizada
# ---------------------------------------------------------------------------

def test_init_com_modelo_customizado():
    cliente = ClienteAnthropic(
        api_key="sk-ant-test",
        model="claude-opus-4-20250514",
    )
    assert cliente.model == "claude-opus-4-20250514"


def test_init_com_extended_thinking_desligado():
    cliente = ClienteAnthropic(
        api_key="sk-ant-test",
        extended_thinking=False,
    )
    assert cliente.extended_thinking is False


def test_init_com_max_tokens_customizado():
    cliente = ClienteAnthropic(
        api_key="sk-ant-test",
        max_tokens=4000,
    )
    assert cliente.max_tokens == 4000


# ---------------------------------------------------------------------------
# GRUPO C — Método classificar()
# ---------------------------------------------------------------------------

def test_classificar_retorna_texto_da_resposta():
    cliente = ClienteAnthropic(api_key="sk-ant-test")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock(
        "classificação aqui"
    )
    cliente._client = mock_client

    resultado = cliente.classificar("prompt de teste")

    assert resultado == "classificação aqui"
    assert mock_client.messages.create.called


def test_classificar_passa_modelo_correto_para_api():
    cliente = ClienteAnthropic(
        api_key="sk-ant-test",
        model="claude-opus-4-20250514",
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock("x")
    cliente._client = mock_client

    cliente.classificar("teste")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-20250514"


def test_classificar_com_extended_thinking_inclui_thinking_param():
    cliente = ClienteAnthropic(
        api_key="sk-ant-test",
        extended_thinking=True,
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock("x")
    cliente._client = mock_client

    cliente.classificar("teste")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "thinking" in call_kwargs
    assert call_kwargs["thinking"]["type"] == "enabled"


def test_classificar_sem_extended_thinking_nao_inclui_thinking_param():
    cliente = ClienteAnthropic(
        api_key="sk-ant-test",
        extended_thinking=False,
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock("x")
    cliente._client = mock_client

    cliente.classificar("teste")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "thinking" not in call_kwargs


def test_classificar_passa_system_prompt_quando_fornecido():
    cliente = ClienteAnthropic(api_key="sk-ant-test")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock("x")
    cliente._client = mock_client

    cliente.classificar("user prompt", system="você é editor")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "você é editor"


def test_classificar_propaga_excecao_da_api():
    cliente = ClienteAnthropic(api_key="sk-ant-test")
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("API down")
    cliente._client = mock_client

    with pytest.raises(RuntimeError, match="API down"):
        cliente.classificar("teste")


# ---------------------------------------------------------------------------
# GRUPO D — Idempotência: temperature determinística (Ciclo 10.1)
# ---------------------------------------------------------------------------
# Decisão 10.1: classificação editorial determinística via temperature=0.0.
# A API exige temperature=1 quando extended thinking está ligado, então só
# enviamos temperature no caminho sem thinking (o usado em produção por
# jornal_diario, que instancia ClienteAnthropic(extended_thinking=False)).

def test_temperature_default_e_zero():
    cliente = ClienteAnthropic(api_key="sk-ant-test")
    assert cliente.temperature == 0.0


def test_classificar_sem_thinking_passa_temperature_zero():
    # Caminho de produção (jornal_diario usa extended_thinking=False).
    cliente = ClienteAnthropic(api_key="sk-ant-test", extended_thinking=False)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock("x")
    cliente._client = mock_client

    cliente.classificar("teste")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["temperature"] == 0.0


def test_classificar_com_thinking_nao_passa_temperature():
    # Guard do conflito: thinking ligado ⇒ temperature deve ser omitida
    # (a API rejeitaria temperature != 1 com thinking habilitado).
    cliente = ClienteAnthropic(api_key="sk-ant-test", extended_thinking=True)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock("x")
    cliente._client = mock_client

    cliente.classificar("teste")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "temperature" not in call_kwargs


def test_classificar_respeita_temperature_customizada():
    cliente = ClienteAnthropic(
        api_key="sk-ant-test",
        extended_thinking=False,
        temperature=0.7,
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _criar_resposta_mock("x")
    cliente._client = mock_client

    cliente.classificar("teste")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["temperature"] == 0.7


# ---------------------------------------------------------------------------
# GRUPO E — Timeouts e retries (Ciclo 10.7a)
# ---------------------------------------------------------------------------
# Decisão 10.7: lote 2025 sofreu 8 hangs de 15-61min com sockets ESTABLISHED
# sem progresso (TCP half-open via IPv6). Defaults da SDK (timeout=600s,
# max_retries=2) seguram demais o pipeline. Reduzir o teto de tempo de
# resposta e aumentar retries dá ao backfill chance de destravar sozinho.


def test_default_timeout_constants_expostas():
    assert ClienteAnthropic.DEFAULT_TIMEOUT_SECONDS == 120.0
    assert ClienteAnthropic.DEFAULT_CONNECT_TIMEOUT_SECONDS == 10.0
    assert ClienteAnthropic.DEFAULT_MAX_RETRIES == 5


def test_init_passa_timeout_default_para_sdk(monkeypatch):
    chamadas: list[dict] = []

    def fake_anthropic(**kwargs):
        chamadas.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        "scripts.cliente_anthropic.anthropic.Anthropic", fake_anthropic,
    )
    ClienteAnthropic(api_key="sk-ant-test")
    timeout = chamadas[0]["timeout"]
    assert timeout.connect == 10.0
    assert timeout.read == 120.0


def test_init_passa_max_retries_default_para_sdk(monkeypatch):
    chamadas: list[dict] = []

    def fake_anthropic(**kwargs):
        chamadas.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        "scripts.cliente_anthropic.anthropic.Anthropic", fake_anthropic,
    )
    ClienteAnthropic(api_key="sk-ant-test")
    assert chamadas[0]["max_retries"] == 5


def test_init_permite_customizar_timeout(monkeypatch):
    import httpx

    chamadas: list[dict] = []

    def fake_anthropic(**kwargs):
        chamadas.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        "scripts.cliente_anthropic.anthropic.Anthropic", fake_anthropic,
    )
    timeout_custom = httpx.Timeout(30.0, connect=5.0)
    ClienteAnthropic(api_key="sk-ant-test", timeout=timeout_custom)
    assert chamadas[0]["timeout"] is timeout_custom


def test_init_permite_customizar_max_retries(monkeypatch):
    chamadas: list[dict] = []

    def fake_anthropic(**kwargs):
        chamadas.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(
        "scripts.cliente_anthropic.anthropic.Anthropic", fake_anthropic,
    )
    ClienteAnthropic(api_key="sk-ant-test", max_retries=10)
    assert chamadas[0]["max_retries"] == 10
