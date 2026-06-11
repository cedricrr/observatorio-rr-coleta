"""Cliente HTTP fino para o Solr (core diarios)."""

from __future__ import annotations

import requests

VERSAO_SCHEMA_SUPORTADA = 1

TIMEOUT_UPDATE = 120
TIMEOUT_SELECT = 30

# commitWithin: o Solr agrupa updates e commita em até 30s — suficiente
# para o fluxo diário e para o backfill, sem custo de commit por request.
COMMIT_WITHIN_MS = 30_000


def explodir_documento(documento: dict) -> list[dict]:
    """Converte um documento de texto (schema versao=1) em docs Solr por página.

    id = {chave_pdf}#{pagina} — reindexar a mesma edição sobrescreve.
    """
    if documento.get("versao") != VERSAO_SCHEMA_SUPORTADA:
        raise ValueError(f"versao de schema não suportada: {documento.get('versao')!r}")
    chave_pdf = documento["chave_pdf"]
    docs = []
    for pagina in documento["paginas"]:
        doc = {
            "id": f"{chave_pdf}#{pagina['n']}",
            "orgao": documento["orgao"],
            "data_edicao": f"{documento['data_edicao']}T00:00:00Z",
            "pagina": pagina["n"],
            "chave_pdf": chave_pdf,
            "texto": pagina["texto"],
        }
        if documento.get("numero") is not None:
            doc["numero"] = documento["numero"]
        docs.append(doc)
    return docs


def enviar_ao_solr(solr_url: str, docs: list[dict]) -> None:
    """Envia docs ao /update do core. Levanta em erro HTTP."""
    resposta = requests.post(
        f"{solr_url}/update",
        params={"commitWithin": COMMIT_WITHIN_MS},
        json=docs,
        timeout=TIMEOUT_UPDATE,
    )
    resposta.raise_for_status()


def consultar_solr(solr_url: str, params: dict) -> dict:
    """Consulta o /select do core e retorna o JSON da resposta."""
    resposta = requests.get(
        f"{solr_url}/select",
        params={**params, "wt": "json"},
        timeout=TIMEOUT_SELECT,
    )
    resposta.raise_for_status()
    return resposta.json()


def ping_solr(solr_url: str) -> bool:
    """True se o core responde ao ping."""
    try:
        resposta = requests.get(f"{solr_url}/admin/ping", timeout=5)
        return resposta.status_code == 200
    except requests.RequestException:
        return False
