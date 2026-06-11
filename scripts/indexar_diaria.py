"""Indexação diária para a busca — chamado pelo GitHub Actions após coleta/publicação.

Para cada edição da data: garante o cache de texto no R2 (dedupe via
r2.existe) e envia ao /indexar da API de busca. Idempotente — os jobs
de coleta, publicação e retry podem todos rodar este passo sem duplicar
nada (overwrite por id no Solr).

Exit 0 quando tudo OK ou quando não há edição na data (dia sem diário
não é erro); 1 só em falha real; 2 em configuração ausente.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from scripts.backfill_indexacao import indexar_chave
from scripts.cache_texto import (
    ORGAOS_VALIDOS,
    chave_pdf_de_metadados,
    chave_texto,
    extrair_e_gravar,
    listar_metadados,
)
from scripts.r2_client import R2Client


def metadados_da_data(
    diarios_dir: Path, data_alvo: date, fontes: list[str],
) -> list[dict]:
    """Metadados das edições de uma data, nas fontes pedidas."""
    alvo = data_alvo.isoformat()
    return [
        m
        for fonte in fontes
        for m in listar_metadados(diarios_dir, fonte)
        if m["data_edicao"] == alvo
    ]


def indexar_data(
    data_alvo: date,
    fontes: list[str],
    diarios_dir: Path,
    r2: R2Client,
    api_url: str,
    token: str,
) -> tuple[int, list[str]]:
    """Garante cache de texto e indexa cada edição da data.

    Retorna (n edições indexadas, lista de erros). Erro em uma edição
    não impede as demais.
    """
    indexadas = 0
    erros: list[str] = []
    for metadados in metadados_da_data(diarios_dir, data_alvo, fontes):
        chave_pdf = chave_pdf_de_metadados(metadados)
        try:
            extrair_e_gravar(metadados, r2)
            indexar_chave(chave_texto(chave_pdf), r2, api_url, token)
            indexadas += 1
        except Exception as e:
            erros.append(f"{chave_pdf}: {e}")
    return indexadas, erros


def main(argv: list[str] | None = None) -> int:
    """Entry point CLI: python -m scripts.indexar_diaria --data hoje --fonte todas"""
    parser = argparse.ArgumentParser(
        description="Indexa as edições de uma data na busca",
    )
    parser.add_argument("--data", default="hoje")
    parser.add_argument("--fonte", choices=ORGAOS_VALIDOS, default="todas")
    parser.add_argument("--diarios-dir", default="data/diarios")

    args = parser.parse_args(argv)

    load_dotenv(Path.cwd() / ".env")
    api_url = os.environ.get("SEARCH_API_URL")
    token = os.environ.get("SEARCH_API_TOKEN")
    if not api_url or not token:
        print(
            "SEARCH_API_URL e SEARCH_API_TOKEN são obrigatórias",
            file=sys.stderr,
        )
        return 2

    if args.data == "hoje":
        data_alvo = date.today()
    elif args.data == "ontem":
        data_alvo = date.today() - timedelta(days=1)
    else:
        data_alvo = date.fromisoformat(args.data)
    fontes = ["mprr", "tjrr"] if args.fonte == "todas" else [args.fonte]

    r2 = R2Client.from_env()
    indexadas, erros = indexar_data(
        data_alvo, fontes, Path(args.diarios_dir), r2, api_url, token,
    )

    if not indexadas and not erros:
        print(f"Sem edição em {data_alvo.isoformat()} — nada a indexar.")
        return 0

    print(f"Indexadas: {indexadas} edição(ões) de {data_alvo.isoformat()}")
    for erro in erros:
        print(f"ERRO: {erro}", file=sys.stderr)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
