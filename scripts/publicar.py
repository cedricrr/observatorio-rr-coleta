"""Publicação do jornal e índice editorial no R2."""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.r2_client import R2Client
from scripts.renderizar import _formatar_data_pt_br

logger = logging.getLogger(__name__)

PREFIXO_R2 = "jornal/"
CHAVE_INDICE = "jornal/index.html"
CONTENT_TYPE_HTML = "text/html; charset=utf-8"
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
    """Renderiza HTML do índice listando todas as edições publicáveis."""
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
                "data": d,
                "data_formatada": _formatar_data_pt_br(d),
                "url": url,
            }
        )
    template = _env.get_template("indice.html.j2")
    return template.render(
        edicoes=edicoes,
        total_edicoes=len(edicoes),
    )


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
    """Publica o jornal do dia e regenera o índice. Retorna (url_jornal, url_indice)."""
    url_jornal = publicar_jornal(html_path, r2, data_edicao)
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
