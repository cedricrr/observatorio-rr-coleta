"""Aplicação FastAPI da busca do Observatório Roraima."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import Config
from app.limites import limiter
from app.rotas_buscar import router as router_buscar
from app.rotas_health import router as router_health
from app.rotas_indexar import router as router_indexar
from app.rotas_leads import router as router_leads


def create_app(config: Config | None = None) -> FastAPI:
    if config is None:
        config = Config.from_env()

    app = FastAPI(title="Busca Observatório RR", docs_url=None, redoc_url=None)
    app.state.config = config
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["X-Sessao", "Content-Type"],
    )

    app.include_router(router_indexar)
    app.include_router(router_buscar)
    app.include_router(router_leads)
    app.include_router(router_health)
    return app
