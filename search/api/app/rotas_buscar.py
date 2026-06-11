"""POST /buscar — busca textual com freemium.

Sem sessão: resposta parcial (contagens + 3 primeiros diários).
Com X-Sessao válido (emitido pelo /leads): lista completa paginada.
Um resultado por DIÁRIO (grouping por chave_pdf), com o trecho da
primeira página onde a chave aparece.
"""

from __future__ import annotations

import html

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.limites import LIMITE_BUSCAR, limiter
from app.sessao import verificar_token
from app.solr import consultar_solr

router = APIRouter()

RESULTADOS_PARCIAL = 3
RESULTADOS_PAGINA = 20
TAMANHO_TRECHO_FALLBACK = 180


class BuscaRequest(BaseModel):
    q: str = Field(min_length=1, max_length=200)
    offset: int = Field(default=0, ge=0)

    @field_validator("q")
    @classmethod
    def _q_nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("q vazio")
        return v.strip()


def _sessao_valida(request: Request) -> bool:
    """True se há sessão válida; 401 se o header veio mas não verifica."""
    token = request.headers.get("X-Sessao")
    if token is None:
        return False
    if not verificar_token(token, request.app.state.config.session_secret):
        raise HTTPException(status_code=401, detail="sessão inválida ou expirada")
    return True


def _montar_params(q: str, completo: bool, offset: int) -> dict:
    return {
        "q": q,
        "defType": "edismax",
        "qf": "texto",
        "pf": "texto",
        "sort": "data_edicao desc",
        "rows": RESULTADOS_PAGINA if completo else RESULTADOS_PARCIAL,
        "start": offset if completo else 0,
        "group": "true",
        "group.field": "chave_pdf",
        "group.limit": 1,
        "group.sort": "pagina asc",
        "group.ngroups": "true",
        "hl": "true",
        "hl.fl": "texto",
    }


def _trecho(doc: dict, highlighting: dict) -> str:
    trechos = highlighting.get(doc["id"], {}).get("texto")
    if trechos:
        return trechos[0]
    return html.escape(doc.get("texto", "")[:TAMANHO_TRECHO_FALLBACK])


def _montar_resultado(doc: dict, highlighting: dict, dominio: str) -> dict:
    chave_pdf = doc["chave_pdf"]
    pagina = doc["pagina"]
    return {
        "orgao": doc["orgao"],
        "data_edicao": doc["data_edicao"].split("T")[0],
        "numero": doc.get("numero"),
        "pagina": pagina,
        "trecho_html": _trecho(doc, highlighting),
        "url_pdf": f"https://{dominio}/{chave_pdf}#page={pagina}",
    }


@router.post("/buscar")
@limiter.limit(LIMITE_BUSCAR)
def buscar(corpo: BuscaRequest, request: Request) -> dict:
    config = request.app.state.config
    completo = _sessao_valida(request)

    resposta = consultar_solr(
        config.solr_url, _montar_params(corpo.q, completo, corpo.offset),
    )

    agrupado = resposta["grouped"]["chave_pdf"]
    highlighting = resposta.get("highlighting", {})
    resultados = [
        _montar_resultado(g["doclist"]["docs"][0], highlighting, config.r2_public_domain)
        for g in agrupado["groups"]
        if g["doclist"]["docs"]
    ]

    return {
        "total_diarios": agrupado["ngroups"],
        "total_ocorrencias": agrupado["matches"],
        "parcial": not completo,
        "offset": corpo.offset if completo else 0,
        "resultados": resultados,
    }
