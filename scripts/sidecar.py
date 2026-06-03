"""Sidecar JSON publicado ao lado de cada jornal/AAAA-MM-DD.html (Sessão 11).

Persiste manchete/resumo/categoria/etc das matérias relevantes para a home
agregar destaques dos últimos 10 jornais sem reprocessar com RLM.
"""

from __future__ import annotations

from datetime import date

from scripts.renderizar import _formatar_data_pt_br
from scripts.segmentar import Materia

SCHEMA_VERSAO = 1


def materia_para_dict_sidecar(m: Materia) -> dict:
    """Converte uma Materia em dict pronto para o sidecar JSON.

    Exclui `texto` (markdown bruto — bloat) e `relevante` (redundante,
    já que apenas matérias relevantes vão para o sidecar).
    """
    return {
        "orgao": m.orgao,
        "tipo": m.tipo,
        "categoria": m.categoria,
        "manchete": m.manchete,
        "resumo": m.resumo,
        "valor_rs": m.valor_rs,
        "tags": m.tags,
        "pdf_url": m.pdf_url,
        "pagina": m.pagina,
    }


def montar_sidecar(
    materias: list[Materia],
    data_edicao: date,
    url_jornal: str,
) -> dict:
    """Monta o dict raiz do sidecar para uma edição.

    Filtra `materias` por `relevante=True`; cada matéria vira dict via
    `materia_para_dict_sidecar`. Cabeçalho inclui versão do schema, data
    em ISO e formato pt-BR (reusa `_formatar_data_pt_br`), URL do jornal
    e contagem de relevantes.
    """
    relevantes = [m for m in materias if m.relevante]
    return {
        "versao": SCHEMA_VERSAO,
        "data_edicao": data_edicao.isoformat(),
        "data_formatada": _formatar_data_pt_br(data_edicao),
        "url_jornal": url_jornal,
        "total_relevantes": len(relevantes),
        "materias": [materia_para_dict_sidecar(m) for m in relevantes],
    }
