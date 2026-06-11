"""Fixtures compartilhadas dos testes da API de busca."""

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.main import create_app


@pytest.fixture
def config() -> Config:
    return Config(
        solr_url="http://solr:8983/solr/diarios",
        database_url="postgresql://leads:leads@localhost:5432/leads",
        search_api_token="tok-teste",
        session_secret="s3gredo-teste",
        cors_allowed_origins=["https://observatoriorr.com.br"],
        r2_public_domain="observatoriorr.com.br",
    )


@pytest.fixture
def client(config) -> TestClient:
    # o limiter é global de módulo — zera o storage entre testes
    from app.limites import limiter

    limiter.reset()
    return TestClient(create_app(config))


@pytest.fixture
def documento_texto() -> dict:
    """Documento de texto no schema versao=1 (contrato com scripts/cache_texto.py)."""
    return {
        "versao": 1,
        "orgao": "mprr",
        "data_edicao": "2022-04-26",
        "numero": 4,
        "chave_pdf": "mprr/2022/04/2022-04-26-4.pdf",
        "sha256_pdf": "abc123",
        "extraido_em": "2026-06-10T12:00:00",
        "extrator": "pymupdf-1.24.0",
        "total_paginas": 2,
        "paginas_vazias": 0,
        "paginas": [
            {"n": 1, "texto": "Portaria nomeando João da Silva"},
            {"n": 2, "texto": "Extrato de contrato com a empresa X"},
        ],
    }
