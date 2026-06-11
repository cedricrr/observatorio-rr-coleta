"""POST /indexar — recebe um documento de texto e indexa por página.

Único endpoint autenticado (Bearer SEARCH_API_TOKEN): é chamado pelo
GitHub Actions no fluxo diário e pelo backfill local. O Solr em si
nunca é exposto.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request

from app.solr import enviar_ao_solr, explodir_documento

router = APIRouter()


def _exigir_token(request: Request) -> None:
    esperado = request.app.state.config.search_api_token
    auth = request.headers.get("Authorization", "")
    prefixo = "Bearer "
    if not auth.startswith(prefixo) or not secrets.compare_digest(
        auth[len(prefixo):], esperado
    ):
        raise HTTPException(status_code=401, detail="token inválido")


@router.post("/indexar")
async def indexar(request: Request) -> dict:
    _exigir_token(request)
    documento = await request.json()
    try:
        docs = explodir_documento(documento)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    enviar_ao_solr(request.app.state.config.solr_url, docs)
    return {"indexadas": len(docs)}
