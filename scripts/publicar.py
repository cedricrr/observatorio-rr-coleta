"""Publicação do jornal e índice editorial no R2."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.r2_client import R2Client
from scripts.renderizar import (
    _formatar_data_abrev,
    _formatar_data_pt_br,
    _formatar_valor_brl,
    _ilustracao_categoria,
    _token_analytics,
)

RESUMO_MAX_CHARS = 280

logger = logging.getLogger(__name__)

PREFIXO_R2 = "jornal/"
CHAVE_INDICE = "jornal/index.html"
# robots/sitemap precisam estar na RAIZ do domínio — única exceção ao
# prefixo jornal/ entre as chaves públicas geradas por este módulo.
CHAVE_ROBOTS = "robots.txt"
CHAVE_SITEMAP = "sitemap.xml"
CONTENT_TYPE_HTML = "text/html; charset=utf-8"
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_TXT = "text/plain; charset=utf-8"
CONTENT_TYPE_XML = "application/xml"
# Índice muda a cada publicação; max-age curto evita servir índice stale do CDN
# (os HTMLs de edição são imutáveis e sobem sem Cache-Control).
CACHE_CONTROL_INDICE = "public, max-age=300"
CACHE_CONTROL_SITEMAP = "public, max-age=3600"
DIARIOS_DIR_DEFAULT = Path("data/diarios")
OUTPUT_DIR_DEFAULT = Path("/tmp/observatorio-roraima")

# Páginas de download de diários por órgão (chave R2 + metadados de exibição).
CHAVE_DIARIOS = {
    "mprr": "jornal/diarios-mprr.html",
    "tjrr": "jornal/diarios-tjrr.html",
}
CHAVE_SOBRE = "jornal/sobre.html"
CHAVE_BUSCA = "jornal/busca.html"
CHAVE_CADASTRO = "jornal/cadastro.html"
CHAVE_PRIVACIDADE = "jornal/privacidade.html"
_META_FONTE = {
    "mprr": {
        "nome": "MPRR",
        "subtitulo": "Ministério Público de Roraima",
        "mostrar_numero": True,
    },
    "tjrr": {
        "nome": "TJRR",
        "subtitulo": "Tribunal de Justiça de Roraima",
        "mostrar_numero": False,
    },
}

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_RE_DATA_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.globals["formatar_valor"] = _formatar_valor_brl
_env.globals["formatar_data"] = _formatar_data_abrev
_env.globals["ilustracao_categoria"] = _ilustracao_categoria


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


def enumerar_diarios_fonte(fonte: str, diarios_dir: Path) -> list[dict]:
    """Lê todos os JSON de data/diarios/<fonte>/ e devolve edições ordenadas desc.

    Cada item: {data_edicao: date, data_formatada: str, numero: int|None,
    url_r2: str|None, tamanho: int|None}. Entradas sem url_r2 são descartadas
    (sem link de download não há linha útil). Dir inexistente → [].
    """
    fonte_dir = diarios_dir / fonte
    if not fonte_dir.exists():
        return []
    edicoes: list[dict] = []
    for json_path in fonte_dir.glob("*.json"):
        meta = json.loads(json_path.read_text(encoding="utf-8"))
        url_r2 = meta.get("url_r2")
        if not url_r2:
            continue
        d = date.fromisoformat(meta["data_edicao"])
        edicoes.append({
            "data_edicao": d,
            "data_formatada": _formatar_data_pt_br(d),
            "numero": meta.get("numero"),
            "url_r2": url_r2,
            "tamanho": meta.get("tamanho"),
        })
    edicoes.sort(key=lambda e: e["data_edicao"], reverse=True)
    return edicoes


def _formatar_tamanho(tamanho: int | None) -> str:
    """Bytes → string legível pt-BR ("1,4 MB" / "781 KB"). None/0 → ""."""
    if not tamanho:
        return ""
    mb = tamanho / 1048576
    if mb >= 1:
        return f"{mb:.1f}".replace(".", ",") + " MB"
    return f"{round(tamanho / 1024)} KB"


_env.globals["formatar_tamanho"] = _formatar_tamanho


def gerar_pagina_diarios(
    fonte: str,
    diarios_dir: Path = DIARIOS_DIR_DEFAULT,
    public_domain: str | None = None,
) -> str:
    """Renderiza a página standalone de diários de uma fonte (mprr/tjrr).

    Lê os JSON locais (não usa R2) e monta seções por ano com links de
    download (url_r2). `url_indice` aponta de volta para a home.
    """
    edicoes = enumerar_diarios_fonte(fonte, diarios_dir)
    anos = agrupar_diarios_por_ano(edicoes)
    meta = _META_FONTE[fonte]
    url_indice = (
        f"https://{public_domain}/{CHAVE_INDICE}" if public_domain else "index.html"
    )
    template = _env.get_template("diarios.html.j2")
    return template.render(
        orgao_nome=meta["nome"],
        orgao_subtitulo=meta["subtitulo"],
        mostrar_numero=meta["mostrar_numero"],
        url_privacidade=_url_privacidade(public_domain),
        anos=anos,
        total=len(edicoes),
        url_indice=url_indice,
        url_sobre=_url_sobre(public_domain),
        url_canonica=(
            f"https://{public_domain}/{CHAVE_DIARIOS[fonte]}" if public_domain else None
        ),
        analytics_token=_token_analytics(),
    )


def agrupar_diarios_por_ano(edicoes: list[dict]) -> list[dict]:
    """Agrupa edições (já em ordem desc) em seções por ano, anos desc.

    Retorna [{"ano": int, "edicoes": [...]}, ...]. A ordem interna de cada
    ano preserva a ordem recebida (desc). [] → [].
    """
    por_ano: dict[int, list[dict]] = {}
    for e in edicoes:
        por_ano.setdefault(e["data_edicao"].year, []).append(e)
    return [
        {"ano": ano, "edicoes": por_ano[ano]}
        for ano in sorted(por_ano, reverse=True)
    ]


def _formatar_milhar(n: int) -> str:
    """Inteiro com separador de milhar pt-BR: 1250 → '1.250'."""
    return f"{n:,}".replace(",", ".")


def resumo_acervo(diarios_dir: Path) -> list[dict]:
    """Estatísticas do acervo por órgão para o painel de busca da home.

    [{orgao, total, total_formatado, ano_min, ano_max}, ...] na ordem
    MPRR, TJRR. Fonte sem edições é omitida. Mesma fonte de dados das
    páginas de diários (JSONs locais via enumerar_diarios_fonte).
    """
    resumo: list[dict] = []
    for fonte in ("mprr", "tjrr"):
        edicoes = enumerar_diarios_fonte(fonte, diarios_dir)
        if not edicoes:
            continue
        anos = [e["data_edicao"].year for e in edicoes]
        ultima = max(e["data_edicao"] for e in edicoes)
        resumo.append({
            "orgao": _META_FONTE[fonte]["nome"],
            "total": len(edicoes),
            "total_formatado": _formatar_milhar(len(edicoes)),
            "ano_min": min(anos),
            "ano_max": max(anos),
            "ultima_edicao_formatada": _formatar_data_abrev(ultima.isoformat()),
        })
    return resumo


def _url_pagina_diarios(fonte: str, public_domain: str | None) -> str:
    """URL da página de diários de uma fonte (absoluta se houver domínio)."""
    chave = CHAVE_DIARIOS[fonte]
    if public_domain:
        return f"https://{public_domain}/{chave}"
    return f"diarios-{fonte}.html"


def _url_sobre(public_domain: str | None) -> str:
    """URL da página Sobre (absoluta se houver domínio)."""
    if public_domain:
        return f"https://{public_domain}/{CHAVE_SOBRE}"
    return "sobre.html"


def _url_api_busca() -> str | None:
    """URL da API de busca (env SEARCH_API_URL). None = busca não implantada.

    Mesmo padrão condicional do CF_ANALYTICS_TOKEN: sem a env, a página
    de busca não é publicada nem linkada — o site funciona sem ela.
    """
    return os.environ.get("SEARCH_API_URL") or None


def _url_busca(public_domain: str | None) -> str:
    """URL da página de busca (absoluta se houver domínio)."""
    if public_domain:
        return f"https://{public_domain}/{CHAVE_BUSCA}"
    return "busca.html"


def _url_privacidade(public_domain: str | None) -> str:
    """URL da política de privacidade (absoluta se houver domínio)."""
    if public_domain:
        return f"https://{public_domain}/{CHAVE_PRIVACIDADE}"
    return "privacidade.html"


def gerar_pagina_busca(public_domain: str | None, api_url: str) -> str:
    """Renderiza a página de busca (form + JS que consome a API no Railway)."""
    url_indice = (
        f"https://{public_domain}/{CHAVE_INDICE}" if public_domain else "index.html"
    )
    template = _env.get_template("busca.html.j2")
    return template.render(
        busca_api_url=api_url.rstrip("/"),
        url_privacidade=_url_privacidade(public_domain),
        url_indice=url_indice,
        url_sobre=_url_sobre(public_domain),
        url_canonica=(
            f"https://{public_domain}/{CHAVE_BUSCA}" if public_domain else None
        ),
        analytics_token=_token_analytics(),
    )


def publicar_pagina_busca(html: str, r2: R2Client) -> str:
    """Sobe a página de busca para jornal/busca.html no R2 (mutável, max-age curto)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)
    try:
        url = r2.upload(
            tmp_path,
            CHAVE_BUSCA,
            content_type=CONTENT_TYPE_HTML,
            cache_control=CACHE_CONTROL_INDICE,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"Página de busca publicada: {url}")
    return url


def _publicar_html_mutavel(html: str, chave: str, r2: R2Client, descricao: str) -> str:
    """Sobe um HTML mutável (max-age curto) para a chave dada."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)
    try:
        url = r2.upload(
            tmp_path,
            chave,
            content_type=CONTENT_TYPE_HTML,
            cache_control=CACHE_CONTROL_INDICE,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"{descricao} publicada: {url}")
    return url


def gerar_pagina_cadastro(public_domain: str | None, api_url: str) -> str:
    """Renderiza a página exclusiva de cadastro (gate do funil — Sessão 13.4)."""
    template = _env.get_template("cadastro.html.j2")
    return template.render(
        busca_api_url=api_url.rstrip("/"),
        url_busca=_url_busca(public_domain),
        url_privacidade=_url_privacidade(public_domain),
        url_indice=(
            f"https://{public_domain}/{CHAVE_INDICE}" if public_domain else "index.html"
        ),
        url_canonica=(
            f"https://{public_domain}/{CHAVE_CADASTRO}" if public_domain else None
        ),
        analytics_token=_token_analytics(),
    )


def publicar_pagina_cadastro(html: str, r2: R2Client) -> str:
    """Sobe a página de cadastro para jornal/cadastro.html no R2."""
    return _publicar_html_mutavel(html, CHAVE_CADASTRO, r2, "Página de cadastro")


def gerar_pagina_privacidade(public_domain: str | None = None) -> str:
    """Renderiza a política de privacidade (LGPD — Sessão 13.4)."""
    template = _env.get_template("privacidade.html.j2")
    return template.render(
        url_indice=(
            f"https://{public_domain}/{CHAVE_INDICE}" if public_domain else "index.html"
        ),
        url_sobre=_url_sobre(public_domain),
        url_canonica=(
            f"https://{public_domain}/{CHAVE_PRIVACIDADE}" if public_domain else None
        ),
        analytics_token=_token_analytics(),
    )


def publicar_pagina_privacidade(html: str, r2: R2Client) -> str:
    """Sobe a política de privacidade para jornal/privacidade.html no R2."""
    return _publicar_html_mutavel(html, CHAVE_PRIVACIDADE, r2, "Política de privacidade")


def gerar_pagina_sobre(public_domain: str | None = None) -> str:
    """Renderiza a página Sobre (identidade, independência, política editorial)."""
    url_indice = (
        f"https://{public_domain}/{CHAVE_INDICE}" if public_domain else "index.html"
    )
    template = _env.get_template("sobre.html.j2")
    return template.render(
        url_indice=url_indice,
        url_privacidade=_url_privacidade(public_domain),
        url_canonica=(
            f"https://{public_domain}/{CHAVE_SOBRE}" if public_domain else None
        ),
        analytics_token=_token_analytics(),
    )


def publicar_pagina_sobre(html: str, r2: R2Client) -> str:
    """Sobe a página Sobre para jornal/sobre.html no R2.

    Mesma política do índice (max-age curto): a página é mutável (muda
    quando o texto institucional evolui).
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)
    try:
        url = r2.upload(
            tmp_path,
            CHAVE_SOBRE,
            content_type=CONTENT_TYPE_HTML,
            cache_control=CACHE_CONTROL_INDICE,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"Página Sobre publicada: {url}")
    return url


def gerar_indice(
    diarios_dir: Path = DIARIOS_DIR_DEFAULT,
    public_domain: str | None = None,
    r2: R2Client | None = None,
) -> str:
    """Renderiza HTML do índice: hero + grid de destaques + links de diários.

    Quando `r2` é fornecido, baixa os sidecars JSON dos jornais mais
    recentes e renderiza hero + grid de destaques (Ciclos 11.7/11.8).
    Sem `r2`, modo degradado: sem hero/grid. O arquivo de edições foi
    substituído por dois links para as páginas de diários por órgão.
    """
    datas = coletar_datas_publicaveis(diarios_dir)
    hero = None
    destaques: list[dict] = []

    if r2 is not None and datas:
        hero, destaques, _ = agregar_destaques_recentes(datas, r2)

    data_ultima = _formatar_data_pt_br(datas[0]) if datas else None
    acervo = resumo_acervo(diarios_dir) if _url_api_busca() else []
    template = _env.get_template("indice.html.j2")
    return template.render(
        hero=hero,
        destaques=destaques,
        total_edicoes=len(datas),
        data_ultima_formatada=data_ultima,
        url_diarios_mprr=_url_pagina_diarios("mprr", public_domain),
        url_diarios_tjrr=_url_pagina_diarios("tjrr", public_domain),
        url_sobre=_url_sobre(public_domain),
        url_busca=_url_busca(public_domain) if _url_api_busca() else None,
        busca_api_url=(_url_api_busca() or "").rstrip("/") or None,
        url_privacidade=_url_privacidade(public_domain),
        acervo=acervo,
        ano_inicio=min((f["ano_min"] for f in acervo), default=None),
        # Canonical da home é a RAIZ do domínio: a Transform Rule do
        # Cloudflare serve / a partir de jornal/index.html.
        url_canonica=f"https://{public_domain}/" if public_domain else None,
        analytics_token=_token_analytics(),
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


def publicar_pagina_diarios(fonte: str, html: str, r2: R2Client) -> str:
    """Sobe a página de diários de uma fonte para jornal/diarios-<fonte>.html.

    Mesma política do índice (max-age curto): a página muda sempre que uma
    nova edição é coletada.
    """
    chave = CHAVE_DIARIOS[fonte]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)
    try:
        url = r2.upload(
            tmp_path,
            chave,
            content_type=CONTENT_TYPE_HTML,
            cache_control=CACHE_CONTROL_INDICE,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"Página de diários ({fonte}) publicada: {url}")
    return url


def publicar_paginas_diarios(
    r2: R2Client,
    diarios_dir: Path = DIARIOS_DIR_DEFAULT,
    public_domain: str | None = None,
) -> list[str]:
    """Gera e publica as páginas de diários de cada fonte. Retorna URLs."""
    urls: list[str] = []
    for fonte in CHAVE_DIARIOS:
        html = gerar_pagina_diarios(fonte, diarios_dir, public_domain=public_domain)
        urls.append(publicar_pagina_diarios(fonte, html, r2))
    return urls


_RE_CHAVE_EDICAO = re.compile(r"^jornal/\d{4}-\d{2}-\d{2}\.html$")


def gerar_robots(public_domain: str) -> str:
    """robots.txt: libera tudo menos os sidecars JSON; aponta o sitemap."""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /jornal/*.json\n"
        "\n"
        f"Sitemap: https://{public_domain}/{CHAVE_SITEMAP}\n"
    )


def gerar_sitemap(r2: R2Client) -> str:
    """Sitemap XML: home (raiz), páginas fixas e todas as edições no R2.

    A fonte da verdade das edições é a listagem do bucket (mesma filosofia
    do dedupe), não os JSONs locais. A home entra como "/" — o canonical
    da Transform Rule — e o index.html não é repetido.
    """
    dominio = r2.public_domain
    urls = [
        f"https://{dominio}/",
        f"https://{dominio}/{CHAVE_SOBRE}",
        f"https://{dominio}/{CHAVE_DIARIOS['mprr']}",
        f"https://{dominio}/{CHAVE_DIARIOS['tjrr']}",
    ]
    if _url_api_busca():
        urls.insert(2, f"https://{dominio}/{CHAVE_BUSCA}")
    edicoes = sorted(
        chave for chave in r2.listar(PREFIXO_R2) if _RE_CHAVE_EDICAO.match(chave)
    )
    urls.extend(f"https://{dominio}/{chave}" for chave in edicoes)
    corpo = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{corpo}\n"
        "</urlset>\n"
    )


def _publicar_texto(
    conteudo: str, chave: str, content_type: str, r2: R2Client,
) -> str:
    """Sobe um artefato textual pequeno (robots/sitemap) com max-age de 1h."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(conteudo)
        tmp_path = Path(tmp.name)
    try:
        url = r2.upload(
            tmp_path,
            chave,
            content_type=content_type,
            cache_control=CACHE_CONTROL_SITEMAP,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"{chave} publicado: {url}")
    return url


def publicar_robots_e_sitemap(r2: R2Client) -> tuple[str, str]:
    """Gera e sobe robots.txt e sitemap.xml na raiz do bucket."""
    url_robots = _publicar_texto(
        gerar_robots(r2.public_domain), CHAVE_ROBOTS, CONTENT_TYPE_TXT, r2,
    )
    url_sitemap = _publicar_texto(
        gerar_sitemap(r2), CHAVE_SITEMAP, CONTENT_TYPE_XML, r2,
    )
    return url_robots, url_sitemap


def publicar_tudo(
    html_path: Path,
    r2: R2Client,
    data_edicao: date,
    diarios_dir: Path = DIARIOS_DIR_DEFAULT,
) -> tuple[str, str]:
    """Publica o jornal do dia, sidecar JSON (se existir), páginas de diários e índice.

    Ordem: jornal HTML → sidecar JSON → páginas de diários (mprr, tjrr) →
    índice. O sidecar é opcional para backward compat com edições geradas
    antes do Ciclo 11.4. As páginas de diários sobem antes do índice para
    os links da home apontarem para páginas frescas no mesmo run.
    """
    url_jornal = publicar_jornal(html_path, r2, data_edicao)
    sidecar_path = html_path.with_suffix(".json")
    if sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        publicar_sidecar(sidecar, r2, data_edicao)
    public_domain = r2.public_domain if hasattr(r2, "public_domain") else None
    publicar_paginas_diarios(r2, diarios_dir, public_domain)
    publicar_pagina_sobre(gerar_pagina_sobre(public_domain), r2)
    publicar_pagina_privacidade(gerar_pagina_privacidade(public_domain), r2)
    api_busca = _url_api_busca()
    if api_busca:
        publicar_pagina_busca(gerar_pagina_busca(public_domain, api_busca), r2)
        publicar_pagina_cadastro(gerar_pagina_cadastro(public_domain, api_busca), r2)
    publicar_robots_e_sitemap(r2)
    html_indice = gerar_indice(
        diarios_dir, public_domain=public_domain, r2=r2,
    )
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
            publicar_paginas_diarios(r2, public_domain=r2.public_domain)
            publicar_pagina_sobre(gerar_pagina_sobre(r2.public_domain), r2)
            publicar_pagina_privacidade(
                gerar_pagina_privacidade(r2.public_domain), r2,
            )
            api_busca = _url_api_busca()
            if api_busca:
                publicar_pagina_busca(
                    gerar_pagina_busca(r2.public_domain, api_busca), r2,
                )
                publicar_pagina_cadastro(
                    gerar_pagina_cadastro(r2.public_domain, api_busca), r2,
                )
            publicar_robots_e_sitemap(r2)
            html = gerar_indice(public_domain=r2.public_domain, r2=r2)
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
