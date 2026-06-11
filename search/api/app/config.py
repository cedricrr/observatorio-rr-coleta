"""Configuração da API via variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    solr_url: str
    database_url: str
    search_api_token: str
    session_secret: str
    cors_allowed_origins: list[str]
    r2_public_domain: str

    @classmethod
    def from_env(cls) -> Config:
        obrigatorias = {
            "SOLR_URL": os.environ.get("SOLR_URL"),
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "SEARCH_API_TOKEN": os.environ.get("SEARCH_API_TOKEN"),
            "SESSION_SECRET": os.environ.get("SESSION_SECRET"),
            "CORS_ALLOWED_ORIGINS": os.environ.get("CORS_ALLOWED_ORIGINS"),
            "R2_PUBLIC_DOMAIN": os.environ.get("R2_PUBLIC_DOMAIN"),
        }
        faltando = [nome for nome, valor in obrigatorias.items() if not valor]
        if faltando:
            raise RuntimeError(f"variáveis de ambiente ausentes: {', '.join(faltando)}")
        return cls(
            solr_url=obrigatorias["SOLR_URL"].rstrip("/"),
            database_url=obrigatorias["DATABASE_URL"],
            search_api_token=obrigatorias["SEARCH_API_TOKEN"],
            session_secret=obrigatorias["SESSION_SECRET"],
            cors_allowed_origins=[
                o.strip() for o in obrigatorias["CORS_ALLOWED_ORIGINS"].split(",") if o.strip()
            ],
            r2_public_domain=obrigatorias["R2_PUBLIC_DOMAIN"],
        )
