"""Rate limiting por IP (slowapi).

Atrás do proxy do Railway o IP real vem em X-Forwarded-For — usa o
primeiro hop; sem o header (dev local), cai no IP da conexão.
/indexar fica isento: já é autenticado por token.
"""

from __future__ import annotations

from slowapi import Limiter
from starlette.requests import Request

LIMITE_BUSCAR = "30/minute"
LIMITE_LEADS = "5/minute"


def _ip_cliente(request: Request) -> str:
    encaminhado = request.headers.get("X-Forwarded-For")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


limiter = Limiter(key_func=_ip_cliente)
