"""Renderização HTML do jornal editorial via Jinja2."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
