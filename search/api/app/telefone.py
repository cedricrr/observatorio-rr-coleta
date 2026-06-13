"""Normalização de telefone brasileiro para E.164 (+55DDDNÚMERO).

Aceita as grafias comuns de formulário (parênteses, hífen, espaços, com ou
sem +55). Sem DDD não há como montar E.164 — devolve None e o endpoint
rejeita, em vez de gravar formato ambíguo.
"""

from __future__ import annotations

import re

RE_NAO_DIGITO = re.compile(r"\D")

# DDD (2) + assinante: fixo 8 dígitos ou celular 9
_TAMANHOS_NACIONAIS = (10, 11)
# com código do país 55 na frente
_TAMANHOS_COM_PAIS = (12, 13)


def normalizar_telefone_br(telefone: str) -> str | None:
    """E.164 BR ou None se não houver DDD + número completos."""
    digitos = RE_NAO_DIGITO.sub("", telefone)
    if digitos.startswith("55") and len(digitos) in _TAMANHOS_COM_PAIS:
        digitos = digitos[2:]
    if len(digitos) in _TAMANHOS_NACIONAIS:
        return f"+55{digitos}"
    return None
