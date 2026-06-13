"""POST /leads — cadastro freemium com consentimento granular (LGPD).

Devolve o token de sessão que libera a lista completa no /buscar.
Contrato da Sessão 13: nome obrigatório, 2 checkboxes (relatórios
obrigatório; ofertas opt-in explícito), termos da sessão e classe
inferida (tecnico/geral) para segmentação editorial.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.classificador import classificar_termos
from app.db import gravar_lead
from app.limites import LIMITE_LEADS, _ip_cliente, limiter
from app.sessao import emitir_token
from app.telefone import normalizar_telefone_br

router = APIRouter()

FINALIDADE = "comunicações do Observatório Roraima"

IP_HASH_HEX_CHARS = 16  # auditoria de consentimento, não anonimização forte


class Consentimentos(BaseModel):
    relatorios: bool
    ofertas: bool = False  # opt-in nunca é assumido

    @field_validator("relatorios")
    @classmethod
    def _relatorios_obrigatorio(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consentimento de relatórios e notificações é obrigatório")
        return v


class LeadRequest(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    email: EmailStr
    telefone: str | None = Field(default=None, max_length=40)
    consentimentos: Consentimentos
    termos: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("nome vazio")
        return v.strip()

    @field_validator("telefone")
    @classmethod
    def _telefone_e164(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalizado = normalizar_telefone_br(v)
        if normalizado is None:
            raise ValueError("telefone inválido — informe DDD + número")
        return normalizado


def _hash_ip(request: Request) -> str:
    return hashlib.sha256(_ip_cliente(request).encode()).hexdigest()[:IP_HASH_HEX_CHARS]


@router.post("/leads", status_code=201)
@limiter.limit(LIMITE_LEADS)
def cadastrar_lead(corpo: LeadRequest, request: Request) -> dict:
    config = request.app.state.config
    gravar_lead(
        config.database_url,
        nome=corpo.nome,
        email=corpo.email,
        telefone=corpo.telefone,
        consentimento_relatorios=corpo.consentimentos.relatorios,
        consentimento_ofertas=corpo.consentimentos.ofertas,
        classe=classificar_termos(corpo.termos),
        termos_sessao=corpo.termos,
        ip_hash=_hash_ip(request),
        finalidade=FINALIDADE,
    )
    return {"token": emitir_token(config.session_secret)}
