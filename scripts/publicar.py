"""Publicação do jornal e índice editorial no R2."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.r2_client import R2Client
from scripts.renderizar import _formatar_data_pt_br, _formatar_valor_brl

RESUMO_MAX_CHARS = 280

logger = logging.getLogger(__name__)

PREFIXO_R2 = "jornal/"
CHAVE_INDICE = "jornal/index.html"
CONTENT_TYPE_HTML = "text/html; charset=utf-8"
CONTENT_TYPE_JSON = "application/json"
# Índice muda a cada publicação; max-age curto evita servir índice stale do CDN
# (os HTMLs de edição são imutáveis e sobem sem Cache-Control).
CACHE_CONTROL_INDICE = "public, max-age=300"
DIARIOS_DIR_DEFAULT = Path("data/diarios")
OUTPUT_DIR_DEFAULT = Path("/tmp/observatorio-roraima")

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_RE_DATA_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.globals["formatar_valor"] = _formatar_valor_brl


def publicar_jornal(
    html_path: Path, r2: R2Client, data_edicao: date,
) -> str:
    """Sobe o HTML do jornal para jornal/AAAA-MM-DD.html no R2."""
    chave = f"{PREFIXO_R2}{data_edicao.isoformat()}.html"
    url = r2.upload(
        html_path,
        chave,
        metadados={"data-edicao": data_edicao.isoformat()},
        content_type=CONTENT_TYPE_HTML,
    )
    logger.info(f"Jornal publicado: {url}")
    return url


def coletar_datas_publicaveis(diarios_dir: Path) -> list[date]:
    """Varre data/diarios/{fonte}/*.json e devolve datas únicas, desc."""
    datas: set[date] = set()
    if not diarios_dir.exists():
        return []
    for fonte_dir in diarios_dir.iterdir():
        if not fonte_dir.is_dir():
            continue
        for json_path in fonte_dir.glob("*.json"):
            m = _RE_DATA_ISO.match(json_path.stem)
            if m:
                datas.add(date.fromisoformat(m.group(1)))
    return sorted(datas, reverse=True)


def gerar_indice(
    diarios_dir: Path = DIARIOS_DIR_DEFAULT,
    public_domain: str | None = None,
) -> str:
    """Renderiza HTML do índice listando todas as edições publicáveis.

    Em modo degradado (sem `r2` / sem sidecars), passa apenas a lista de
    `edicoes` com `total_relevantes=0`; hero e destaques ficam vazios.
    """
    datas = coletar_datas_publicaveis(diarios_dir)
    edicoes = []
    for d in datas:
        iso = d.isoformat()
        if public_domain:
            url = f"https://{public_domain}/{PREFIXO_R2}{iso}.html"
        else:
            url = f"{iso}.html"
        edicoes.append(
            {
                "data_edicao": iso,
                "data_formatada": _formatar_data_pt_br(d),
                "url_jornal": url,
                "total_relevantes": 0,
            }
        )
    data_ultima = _formatar_data_pt_br(datas[0]) if datas else None
    template = _env.get_template("indice.html.j2")
    return template.render(
        hero=None,
        destaques=[],
        edicoes=edicoes,
        total_edicoes=len(edicoes),
        data_ultima_formatada=data_ultima,
    )


def publicar_sidecar(
    sidecar: dict, r2: R2Client, data_edicao: date,
) -> str:
    """Sobe o sidecar JSON para jornal/AAAA-MM-DD.json no R2.

    JSON é serializado com `indent=2` e `ensure_ascii=False` para
    preservar acentos como UTF-8 (legível em curl/jq). Sidecar é
    imutável como o HTML do jornal — sem Cache-Control.
    """
    chave = f"{PREFIXO_R2}{data_edicao.isoformat()}.json"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    ) as tmp:
        json.dump(sidecar, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    try:
        url = r2.upload(
            tmp_path,
            chave,
            metadados={"data-edicao": data_edicao.isoformat()},
            content_type=CONTENT_TYPE_JSON,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"Sidecar publicado: {url}")
    return url


def baixar_sidecar(data_edicao: date, r2: R2Client) -> dict | None:
    """Baixa e parseia jornal/AAAA-MM-DD.json do R2. None se 404/NoSuchKey."""
    chave = f"{PREFIXO_R2}{data_edicao.isoformat()}.json"
    try:
        bytes_ = r2.download_bytes(chave)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NoSuchBucket"):
            return None
        raise
    return json.loads(bytes_.decode("utf-8"))


def _truncar_resumo(texto: str | None) -> str | None:
    """Trunca resumo a RESUMO_MAX_CHARS adicionando reticência se cortou."""
    if texto is None or len(texto) <= RESUMO_MAX_CHARS:
        return texto
    return texto[:RESUMO_MAX_CHARS].rstrip() + "…"


def _ordem_destaque(item: dict) -> tuple:
    """Chave de ordenação: (data desc, valor desc com None=0)."""
    return (
        item["_data"],
        item["materia"]["valor_rs"] or 0,
    )


def agregar_destaques_recentes(
    datas: list[date],
    r2: R2Client,
    n_sidecars: int = 10,
    k_destaques: int = 8,
) -> tuple[dict | None, list[dict], list[dict]]:
    """Baixa os N sidecars mais recentes e escolhe top-K matérias.

    Ordena por (data_edicao desc, valor_rs desc com None=0).
    Retorna (hero, grid, edicoes_meta):
      - hero = top-1 (ou None se nada);
      - grid = próximos K-1 (até K-1 cards);
      - edicoes_meta = lista de dicts {data_edicao, data_formatada,
        url_jornal, total_relevantes} para a seção "Arquivo".

    `resumo` é truncado a 280 chars no item retornado; o sidecar no R2
    permanece integral.
    """
    edicoes_meta: list[dict] = []
    candidatos: list[dict] = []
    for d in datas[:n_sidecars]:
        sidecar = baixar_sidecar(d, r2)
        if sidecar is None:
            continue
        edicoes_meta.append({
            "data_edicao": sidecar["data_edicao"],
            "data_formatada": sidecar["data_formatada"],
            "url_jornal": sidecar["url_jornal"],
            "total_relevantes": sidecar["total_relevantes"],
        })
        for m in sidecar["materias"]:
            candidatos.append({"_data": d, "materia": m})

    candidatos.sort(key=_ordem_destaque, reverse=True)
    top = candidatos[:k_destaques]

    def _vista(item: dict) -> dict:
        m = dict(item["materia"])
        m["resumo"] = _truncar_resumo(m.get("resumo"))
        m["data_edicao"] = item["_data"].isoformat()
        return m

    if not top:
        return None, [], edicoes_meta

    hero = _vista(top[0])
    grid = [_vista(it) for it in top[1:]]
    return hero, grid, edicoes_meta


def publicar_indice(html_indice: str, r2: R2Client) -> str:
    """Sobe o índice HTML para jornal/index.html no R2."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(html_indice)
        tmp_path = Path(tmp.name)
    try:
        url = r2.upload(
            tmp_path,
            CHAVE_INDICE,
            content_type=CONTENT_TYPE_HTML,
            cache_control=CACHE_CONTROL_INDICE,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"Índice publicado: {url}")
    return url


def publicar_tudo(
    html_path: Path,
    r2: R2Client,
    data_edicao: date,
    diarios_dir: Path = DIARIOS_DIR_DEFAULT,
) -> tuple[str, str]:
    """Publica o jornal do dia, sidecar JSON (se existir) e regenera o índice.

    Ordem: jornal HTML → sidecar JSON → índice. O sidecar é opcional para
    backward compat com edições geradas antes do Ciclo 11.4.
    """
    url_jornal = publicar_jornal(html_path, r2, data_edicao)
    sidecar_path = html_path.with_suffix(".json")
    if sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        publicar_sidecar(sidecar, r2, data_edicao)
    public_domain = r2.public_domain if hasattr(r2, "public_domain") else None
    html_indice = gerar_indice(diarios_dir, public_domain=public_domain)
    url_indice = publicar_indice(html_indice, r2)
    return url_jornal, url_indice


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publica jornal editorial e índice no R2",
    )
    parser.add_argument(
        "--data", default="hoje",
        help="Data da edição (ISO yyyy-mm-dd ou 'hoje'). Default: hoje.",
    )
    parser.add_argument(
        "--html-path", type=Path, default=None,
        help=f"Path do HTML local. Default: {OUTPUT_DIR_DEFAULT}/<data>.html.",
    )
    parser.add_argument(
        "--apenas-indice", action="store_true",
        help="Não publica jornal, só regenera o índice.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv)

    if args.data == "hoje":
        data_edicao = date.today()
    else:
        data_edicao = date.fromisoformat(args.data)

    r2 = R2Client.from_env()

    try:
        if args.apenas_indice:
            html = gerar_indice(public_domain=r2.public_domain)
            url = publicar_indice(html, r2)
            print(f"Índice publicado: {url}")
        else:
            html_path = args.html_path or (
                OUTPUT_DIR_DEFAULT / f"{data_edicao.isoformat()}.html"
            )
            if not html_path.exists():
                logger.error(f"HTML não existe: {html_path}")
                return 1
            url_jornal, url_indice = publicar_tudo(html_path, r2, data_edicao)
            print(f"Jornal:  {url_jornal}")
            print(f"Índice:  {url_indice}")
        return 0
    except Exception as e:
        logger.error(f"Falha na publicação: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
