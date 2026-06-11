"""GET /health — checa Solr (ping) e Postgres (SELECT 1)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db import ping_db
from app.solr import ping_solr

router = APIRouter()


@router.get("/health")
def health(request: Request) -> JSONResponse:
    config = request.app.state.config
    solr_ok = ping_solr(config.solr_url)
    db_ok = ping_db(config.database_url)
    status = 200 if (solr_ok and db_ok) else 503
    return JSONResponse({"solr": solr_ok, "db": db_ok}, status_code=status)
