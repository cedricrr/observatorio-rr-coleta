"""Sidecar JSON publicado ao lado de cada jornal/AAAA-MM-DD.html (Sessão 11).

Persiste manchete/resumo/categoria/etc das matérias relevantes para a home
agregar destaques dos últimos 10 jornais sem reprocessar com RLM.
"""

from __future__ import annotations

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
