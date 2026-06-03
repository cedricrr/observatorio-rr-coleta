"""Wrapper sobre anthropic.Anthropic com extended thinking configurável."""

from __future__ import annotations

import os

import anthropic
import httpx


class ClienteAnthropic:
    """Cliente para classificação editorial via Claude API.

    Encapsula configuração (modelo, extended thinking, max_tokens) e
    expõe método classificar() simples. Centraliza tratamento de
    autenticação via SDK anthropic e parâmetros do modelo.

    A SDK anthropic.Anthropic lê ANTHROPIC_API_KEY do ambiente
    automaticamente quando api_key não é passado. Se a key não
    existir em lugar nenhum, a SDK levanta AuthenticationError no
    primeiro uso.
    """

    DEFAULT_MODEL = "claude-sonnet-4-6"
    DEFAULT_MAX_TOKENS = 2000
    THINKING_BUDGET_TOKENS = 1024
    DEFAULT_TEMPERATURE = 0.0
    DEFAULT_TIMEOUT_SECONDS = 120.0
    DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
    DEFAULT_MAX_RETRIES = 5

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        extended_thinking: bool = True,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: httpx.Timeout | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        if api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError(
                "ANTHROPIC_API_KEY não definida (nem como argumento "
                "nem como variável de ambiente)"
            )
        if timeout is None:
            # Ciclo 10.7: teto curto de leitura destrava socket half-open
            # antes de o backfill estagnar (defaults da SDK seguram 600s).
            timeout = httpx.Timeout(
                self.DEFAULT_TIMEOUT_SECONDS,
                connect=self.DEFAULT_CONNECT_TIMEOUT_SECONDS,
            )
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries,
        )
        self.model = model
        self.extended_thinking = extended_thinking
        self.max_tokens = max_tokens
        self.temperature = temperature

    def classificar(
        self,
        prompt: str,
        system: str | None = None,
    ) -> str:
        """Envia prompt à API, retorna texto da resposta.

        Quando extended_thinking=True, adiciona parâmetro thinking
        com budget mínimo (1024 tokens). Sem extended_thinking, a
        chamada é direta — modelo responde sem etapa de raciocínio
        explícito.

        Quando system é fornecido, é passado como system prompt
        (distinto do user prompt). Senão é omitido.

        Retorna o texto do primeiro bloco de conteúdo da resposta.
        Para respostas com extended thinking, blocos de thinking
        aparecem ANTES do bloco de texto final — esta função busca
        o primeiro bloco type="text" e ignora blocos de thinking.

        Exceções da API (rate limit, timeout, auth) são propagadas
        sem captura.
        """
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system is not None:
            kwargs["system"] = system

        if self.extended_thinking:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.THINKING_BUDGET_TOKENS,
            }
        else:
            # Idempotência (Ciclo 10.1): temperatura determinística só é
            # aceita pela API sem extended thinking — com thinking ligado a
            # API exige temperature=1, então omitimos o parâmetro nesse caso.
            kwargs["temperature"] = self.temperature

        resposta = self._client.messages.create(**kwargs)

        for bloco in resposta.content:
            if getattr(bloco, "type", None) == "text":
                return bloco.text

        return resposta.content[0].text
