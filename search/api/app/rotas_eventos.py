"""POST /eventos — etapas do funil (home → busca → gate → cadastro).

Evento anterior ao consentimento: o payload é fechado (extra="forbid")
e carrega só o tipo e um id de sessão anônimo gerado no cliente.
Nada de IP, user agent ou dado pessoal — nem aqui, nem na tabela.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.db import gravar_evento
from app.limites import LIMITE_EVENTOS, limiter

router = APIRouter()


class EventoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["home_view", "busca_exec", "gate_view", "cadastro_ok"]
    sessao: str = Field(min_length=1, max_length=64)


@router.post("/eventos", status_code=201)
@limiter.limit(LIMITE_EVENTOS)
def registrar_evento(corpo: EventoRequest, request: Request) -> dict:
    gravar_evento(
        request.app.state.config.database_url,
        tipo=corpo.tipo,
        sessao_id=corpo.sessao,
    )
    return {}
