"""Parser HTML → sidecar dict para retro-popular edições já publicadas.

Edições publicadas antes do Ciclo 11.4 não têm sidecar JSON. Este módulo
reconstrói o dict a partir do HTML do jornal usando BeautifulSoup. Campos
não recuperáveis (texto markdown bruto, tipo da matéria, número da página)
ficam com defaults seguros (None ou string sentinela).
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from scripts.renderizar import _formatar_data_pt_br
from scripts.sidecar import SCHEMA_VERSAO

# Valor em formato brasileiro: "152.340,50" → 152340.50
_RE_VALOR = re.compile(r"R\$\s*([\d.]+,\d{2})")

# tipo não é exposto no HTML — usar sentinela para diferenciar de "não preenchido"
TIPO_DESCONHECIDO = "DESCONHECIDO"


def _parsear_valor_brl(texto: str) -> float | None:
    """Extrai número BRL ("R$ 1.234,56") de um texto. None se não casar."""
    m = _RE_VALOR.search(texto)
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def _extrair_materia(article, orgao: str) -> dict:
    """Extrai um <article class="materia"> em dict do schema sidecar."""
    h3 = article.find("h3")
    manchete = h3.get_text(strip=True) if h3 else None

    p_resumo = article.find("p", class_="resumo")
    resumo = p_resumo.get_text(strip=True) if p_resumo else None

    meta = article.find("div", class_="meta-materia")
    categoria = None
    tags: list[str] = []
    valor_rs: float | None = None
    if meta is not None:
        cat_span = meta.find("span", class_="categoria")
        if cat_span is not None:
            categoria = cat_span.get_text(strip=True)
        valor_span = meta.find("span", class_="valor")
        if valor_span is not None:
            valor_rs = _parsear_valor_brl(valor_span.get_text())
        for tag in meta.find_all("span", class_="tag"):
            if "categoria" in tag.get("class", []):
                continue
            tags.append(tag.get_text(strip=True))

    pdf_url = None
    p_fonte = article.find("p", class_="fonte")
    if p_fonte is not None:
        a = p_fonte.find("a")
        if a is not None and a.get("href"):
            pdf_url = a["href"]

    return {
        "orgao": orgao,
        "tipo": TIPO_DESCONHECIDO,
        "categoria": categoria,
        "manchete": manchete,
        "resumo": resumo,
        "valor_rs": valor_rs,
        "tags": tags,
        "pdf_url": pdf_url,
        "pagina": None,
    }


def parse_jornal_para_sidecar(
    html: str, data_edicao: date, url_jornal: str,
) -> dict:
    """Parseia o HTML de um jornal já publicado e devolve dict do sidecar.

    Idempotente: chamadas repetidas com o mesmo HTML devolvem dicts iguais.
    Empty-state (sem `section.orgao`) → `materias=[]`.
    """
    soup = BeautifulSoup(html, "html.parser")
    materias: list[dict] = []
    for section in soup.find_all("section", class_="orgao"):
        h2 = section.find("h2")
        orgao = h2.get_text(strip=True) if h2 else ""
        for article in section.find_all("article", class_="materia"):
            materias.append(_extrair_materia(article, orgao))
    return {
        "versao": SCHEMA_VERSAO,
        "data_edicao": data_edicao.isoformat(),
        "data_formatada": _formatar_data_pt_br(data_edicao),
        "url_jornal": url_jornal,
        "total_relevantes": len(materias),
        "materias": materias,
    }
