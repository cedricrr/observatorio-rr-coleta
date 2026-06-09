"""Renderização HTML do jornal editorial via Jinja2."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from scripts.segmentar import Materia

ORDEM_ORGAOS = ["MPRR", "TJRR"]

_MESES_PT_BR = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

_MESES_ABREV_PT_BR = [
    "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
    "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
]


def _formatar_data_pt_br(d: date) -> str:
    return f"{d.day} de {_MESES_PT_BR[d.month - 1]} de {d.year}"


def _formatar_data_abrev(iso: str | None) -> str:
    """ISO "YYYY-MM-DD" → "08 JUN 2026" (mês abreviado PT-BR). Falsy → ""."""
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.day:02d} {_MESES_ABREV_PT_BR[d.month - 1]} {d.year}"


def _formatar_valor_brl(valor: float) -> str:
    formatado_us = f"{valor:,.2f}"
    return formatado_us.replace(",", "_").replace(".", ",").replace("_", ".")


# ---------------------------------------------------------------------------
# Ilustração SVG temática da coluna direita do hero (índice da home).
# Determinística: o motivo é escolhido pela categoria do destaque e a cor
# de acento pelo órgão. Sem dependências externas — SVG inline.
# ---------------------------------------------------------------------------

_ILUSTRA_INK = "#1a1a1a"

_ACENTO_ORGAO = {
    "MPRR": "#c8102e",
    "TJRR": "#1d4e89",
}
_ACENTO_PADRAO = "#c8102e"

# Cada motivo usa os placeholders {ink} e {accent}; viewBox 0 0 200 200.
_MOTIVO_PADRAO = (
    '<rect x="56" y="58" width="80" height="66" rx="5" fill="#fff" stroke="{ink}" stroke-width="4"/>'
    '<rect x="66" y="70" width="28" height="22" fill="none" stroke="{accent}" stroke-width="3.5"/>'
    '<line x1="100" y1="72" x2="126" y2="72" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
    '<line x1="100" y1="82" x2="126" y2="82" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
    '<line x1="100" y1="92" x2="120" y2="92" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
    '<line x1="66" y1="104" x2="126" y2="104" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
    '<line x1="66" y1="114" x2="110" y2="114" stroke="{ink}" stroke-width="3.5" stroke-linecap="round"/>'
)

_MOTIVOS_CATEGORIA = {
    "Contratos e licitações": (
        '<rect x="58" y="46" width="60" height="82" rx="5" fill="#fff" stroke="{ink}" stroke-width="4"/>'
        '<line x1="70" y1="68" x2="106" y2="68" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        '<line x1="70" y1="84" x2="106" y2="84" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        '<line x1="70" y1="100" x2="92" y2="100" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="122" cy="124" r="22" fill="#fff" stroke="{accent}" stroke-width="4"/>'
        '<text x="122" y="131" text-anchor="middle" font-family="Georgia, serif"'
        ' font-size="17" font-weight="700" fill="{accent}">R$</text>'
    ),
    "Movimentação de pessoal": (
        '<circle cx="72" cy="82" r="13" fill="none" stroke="{ink}" stroke-width="4"/>'
        '<path d="M54 120 q18 -26 36 0" fill="none" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="128" cy="82" r="13" fill="none" stroke="{accent}" stroke-width="4"/>'
        '<path d="M110 120 q18 -26 36 0" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>'
        '<path d="M88 100 h24" fill="none" stroke="{accent}" stroke-width="3.5" stroke-linecap="round"/>'
        '<path d="M106 94 l8 6 -8 6" fill="none" stroke="{accent}" stroke-width="3.5"'
        ' stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "Investigações e inquéritos": (
        '<circle cx="90" cy="88" r="32" fill="#fff" stroke="{ink}" stroke-width="4"/>'
        '<path d="M78 88 a12 12 0 0 1 12 -12" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>'
        '<line x1="114" y1="112" x2="142" y2="140" stroke="{accent}" stroke-width="7" stroke-linecap="round"/>'
    ),
    "Atos normativos": (
        '<rect x="58" y="44" width="64" height="86" rx="5" fill="#fff" stroke="{ink}" stroke-width="4"/>'
        '<text x="90" y="104" text-anchor="middle" font-family="Georgia, serif"'
        ' font-size="52" fill="{accent}">§</text>'
    ),
    "Designações e nomeações": (
        '<path d="M86 102 l-12 32 16 -9 8 13 8 -13 16 9 -12 -32" fill="none"'
        ' stroke="{ink}" stroke-width="3.5" stroke-linejoin="round"/>'
        '<circle cx="100" cy="82" r="28" fill="#fff" stroke="{accent}" stroke-width="4"/>'
        '<text x="100" y="92" text-anchor="middle" font-family="Georgia, serif"'
        ' font-size="30" fill="{accent}">★</text>'
    ),
    "Concursos e delegações": (
        '<rect x="62" y="52" width="60" height="80" rx="6" fill="#fff" stroke="{ink}" stroke-width="4"/>'
        '<rect x="82" y="44" width="20" height="14" rx="3" fill="#fff" stroke="{ink}" stroke-width="4"/>'
        '<path d="M72 78 l6 6 11 -13" fill="none" stroke="{accent}" stroke-width="4"'
        ' stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M72 104 l6 6 11 -13" fill="none" stroke="{accent}" stroke-width="4"'
        ' stroke-linecap="round" stroke-linejoin="round"/>'
        '<line x1="98" y1="78" x2="114" y2="78" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        '<line x1="98" y1="104" x2="114" y2="104" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
    ),
    "Cessões e cooperações": (
        '<path d="M62 92 A 44 44 0 0 1 138 84" fill="none" stroke="{ink}"'
        ' stroke-width="4" stroke-linecap="round"/>'
        '<path d="M138 84 l-3 -15 16 7" fill="none" stroke="{ink}" stroke-width="4"'
        ' stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M138 108 A 44 44 0 0 1 62 116" fill="none" stroke="{accent}"'
        ' stroke-width="4" stroke-linecap="round"/>'
        '<path d="M62 116 l3 15 -16 -7" fill="none" stroke="{accent}" stroke-width="4"'
        ' stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "Decisões judiciais relevantes": (
        '<line x1="100" y1="50" x2="100" y2="128" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        '<line x1="66" y1="64" x2="134" y2="64" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="100" cy="50" r="5" fill="{accent}"/>'
        '<path d="M66 64 L54 92 a16 10 0 0 0 24 0 Z" fill="none" stroke="{accent}"'
        ' stroke-width="3.5" stroke-linejoin="round"/>'
        '<path d="M134 64 L122 92 a16 10 0 0 0 24 0 Z" fill="none" stroke="{accent}"'
        ' stroke-width="3.5" stroke-linejoin="round"/>'
        '<line x1="82" y1="132" x2="118" y2="132" stroke="{ink}" stroke-width="4" stroke-linecap="round"/>'
    ),
    "Outros": _MOTIVO_PADRAO,
}


def _ilustracao_categoria(categoria: str | None, orgao: str | None = None) -> Markup:
    """SVG inline temático para a categoria do hero, com acento por órgão."""
    accent = _ACENTO_ORGAO.get((orgao or "").strip().upper(), _ACENTO_PADRAO)
    motivo = _MOTIVOS_CATEGORIA.get(categoria or "", _MOTIVO_PADRAO)
    rotulo = escape(categoria or "matéria em destaque")
    svg = (
        '<svg class="ilustra-svg" viewBox="0 0 200 200"'
        ' xmlns="http://www.w3.org/2000/svg" role="img"'
        f' aria-label="Ilustração: {rotulo}">'
        f'<circle cx="100" cy="100" r="82" fill="{accent}" opacity="0.06"/>'
        f'{motivo.format(ink=_ILUSTRA_INK, accent=accent)}'
        '</svg>'
    )
    return Markup(svg)


def _agrupar_por_orgao(
    materias: list[Materia],
) -> dict[str, list[Materia]]:
    orgaos_presentes = {m.orgao for m in materias}
    ordem_final = [o for o in ORDEM_ORGAOS if o in orgaos_presentes]
    extras = sorted(orgaos_presentes - set(ORDEM_ORGAOS))
    ordem_final.extend(extras)

    agrupado: dict[str, list[Materia]] = {}
    for orgao in ordem_final:
        agrupado[orgao] = [m for m in materias if m.orgao == orgao]
    return agrupado


_TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

_env.globals["formatar_valor"] = _formatar_valor_brl


def renderizar_jornal(
    materias: list[Materia],
    data_edicao: date,
    num_edicao: int | None = None,
) -> str:
    """Renderiza HTML do jornal editorial a partir de matérias classificadas.

    Filtra matérias com relevante=False (rotina administrativa).
    Agrupa por órgão (MPRR primeiro, TJRR depois).
    Retorna documento HTML completo auto-contido.
    """
    relevantes = [m for m in materias if m.relevante]
    materias_por_orgao = _agrupar_por_orgao(relevantes)
    data_formatada = _formatar_data_pt_br(data_edicao)

    template = _env.get_template("jornal.html.j2")
    return template.render(
        data_formatada=data_formatada,
        num_edicao=num_edicao,
        total_materias=len(relevantes),
        materias_por_orgao=materias_por_orgao,
    )
