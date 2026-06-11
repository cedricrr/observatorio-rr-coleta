"""POST /leads — cadastro freemium com consentimento explícito (LGPD).

Devolve o token de sessão que libera a lista completa no /buscar.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.db import gravar_lead
from app.limites import LIMITE_LEADS, limiter
from app.sessao import emitir_token

router = APIRouter()

FINALIDADE = "comunicações do Observatório Roraima"


class LeadRequest(BaseModel):
    email: EmailStr
    telefone: str | None = Field(default=None, max_length=40)
    consentimento: bool
    origem_busca: str | None = Field(default=None, max_length=200)


@router.post("/leads")
@limiter.limit(LIMITE_LEADS)
def cadastrar_lead(corpo: LeadRequest, request: Request) -> dict:
    if corpo.consentimento is not True:
        raise HTTPException(status_code=400, detail="consentimento é obrigatório")

    config = request.app.state.config
    gravar_lead(
        config.database_url,
        email=corpo.email,
        telefone=corpo.telefone,
        finalidade=FINALIDADE,
        origem_busca=corpo.origem_busca,
    )
    return {"token": emitir_token(config.session_secret)}
