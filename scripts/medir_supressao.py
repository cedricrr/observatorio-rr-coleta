"""Medição SOMENTE LEITURA da supressão no índice de busca (Sessão 12).

Varre texto/ no R2 aplicando as regras de search/api/app/filtro_sensivel.py
(fonte única — a medição mede exatamente o que o /indexar vai filtrar) e
grava relatório em data/incidentes/ (gitignored: os trechos casados são
conteúdo sensível e não vão para git nem R2).

Nada sobe ao R2 nem ao Solr. Uso:

    python -m scripts.medir_supressao                 # acervo completo
    python -m scripts.medir_supressao --orgao tjrr --limite 50
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.r2_client import R2Client

logger = logging.getLogger(__name__)

CAMINHO_FILTRO = (
    Path(__file__).resolve().parent.parent / "search" / "api" / "app" / "filtro_sensivel.py"
)
DIR_INCIDENTES = Path("data/incidentes")
TRECHO_MAX = 200
LOG_A_CADA = 100


def carregar_filtro():
    """Carrega pagina_sensivel do módulo da API por caminho de arquivo.

    O módulo é puro e só-stdlib (contrato documentado nele), então roda
    no venv do coletor sem instalar as deps do FastAPI.
    """
    spec = importlib.util.spec_from_file_location("filtro_sensivel", CAMINHO_FILTRO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.pagina_sensivel


def medir_documento(doc: dict, pagina_sensivel) -> list[dict]:
    """Páginas sensíveis de um documento texto/ (schema versao 1)."""
    achados: list[dict] = []
    for pagina in doc.get("paginas", []):
        texto = pagina.get("texto", "")
        regra = pagina_sensivel(texto)
        if regra:
            achados.append({
                "chave_pdf": doc["chave_pdf"],
                "orgao": doc["orgao"],
                "data_edicao": doc["data_edicao"],
                "pagina": pagina["n"],
                "regra": regra,
                "trecho": texto.strip()[:TRECHO_MAX],
            })
    return achados


def executar_medicao(
    r2: R2Client,
    orgao: str | None = None,
    limite: int | None = None,
    agora: datetime | None = None,
) -> dict:
    """Varre texto/ no R2 e devolve o relatório agregado (nada sobe)."""
    pagina_sensivel = carregar_filtro()
    prefixo = f"texto/{orgao}/" if orgao else "texto/"
    chaves = r2.listar(prefixo)
    if limite is not None:
        chaves = chaves[:limite]

    por_orgao_ano: dict = {}
    por_regra: dict[str, int] = {}
    achados: list[dict] = []
    erros: list[str] = []
    total_documentos = 0
    total_paginas = 0

    for chave in chaves:
        try:
            doc = json.loads(r2.download_bytes(chave))
            doc_achados = medir_documento(doc, pagina_sensivel)
            ano = str(doc["data_edicao"])[:4]
            orgao_doc = doc["orgao"]
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"documento ilegível, pulando: {chave} ({e})")
            erros.append(chave)
            continue

        total_documentos += 1
        n_paginas = len(doc.get("paginas", []))
        total_paginas += n_paginas
        bucket = por_orgao_ano.setdefault(orgao_doc, {}).setdefault(
            ano, {"paginas": 0, "suprimidas": 0},
        )
        bucket["paginas"] += n_paginas
        bucket["suprimidas"] += len(doc_achados)
        for achado in doc_achados:
            por_regra[achado["regra"]] = por_regra.get(achado["regra"], 0) + 1
        achados.extend(doc_achados)

        if total_documentos % LOG_A_CADA == 0:
            logger.info(
                f"{total_documentos}/{len(chaves)} documentos · "
                f"{len(achados)} páginas sensíveis até aqui"
            )

    if agora is None:
        agora = datetime.now(timezone.utc)
    return {
        "executado_em_utc": agora.isoformat(),
        "parametros": {"orgao": orgao, "limite": limite},
        "total_documentos": total_documentos,
        "total_paginas": total_paginas,
        "total_paginas_suprimidas": len(achados),
        "documentos_com_erro": erros,
        "por_orgao_ano": por_orgao_ano,
        "por_regra": por_regra,
        "achados": achados,
    }


def gravar_relatorio(
    relatorio: dict,
    dir_destino: Path = DIR_INCIDENTES,
    agora: datetime | None = None,
) -> Path:
    """Grava o relatório em data/incidentes/ (gitignored) e devolve o path."""
    if agora is None:
        agora = datetime.now(timezone.utc)
    dir_destino.mkdir(parents=True, exist_ok=True)
    caminho = dir_destino / f"medicao-supressao-{agora.strftime('%Y%m%dT%H%M%SZ')}.json"
    caminho.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return caminho


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Medição read-only da supressão no índice (nada sobe)",
    )
    parser.add_argument("--orgao", choices=["mprr", "tjrr"], default=None)
    parser.add_argument("--limite", type=int, default=None)
    args = parser.parse_args(argv)

    r2 = R2Client.from_env()
    relatorio = executar_medicao(r2, orgao=args.orgao, limite=args.limite)
    caminho = gravar_relatorio(relatorio)

    # resumo SEM trechos no stdout — conteúdo sensível fica só no arquivo local
    taxa = (
        relatorio["total_paginas_suprimidas"] / relatorio["total_paginas"] * 100
        if relatorio["total_paginas"] else 0.0
    )
    print(f"Documentos: {relatorio['total_documentos']} "
          f"(erros: {len(relatorio['documentos_com_erro'])})")
    print(f"Páginas: {relatorio['total_paginas']} · "
          f"sensíveis: {relatorio['total_paginas_suprimidas']} ({taxa:.2f}%)")
    print(f"Por regra: {relatorio['por_regra']}")
    for orgao_nome, anos in sorted(relatorio["por_orgao_ano"].items()):
        for ano, b in sorted(anos.items()):
            print(f"  {orgao_nome}/{ano}: {b['suprimidas']}/{b['paginas']} páginas")
    print(f"Relatório completo (gitignored): {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
