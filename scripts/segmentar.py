"""Segmentação de matérias em diários oficiais (Markdown) por órgão."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Materia:
    """Uma unidade publicada no diário, identificada por padrão regex."""
    # Campos identificadores (do Ciclo 8.4)
    orgao: str
    tipo: str
    texto: str
    pdf_url: str
    pagina: int | None = None

    # Campos de classificação editorial (Sub-ciclos 8.6+)
    # Preenchidos pelo classificador RLM. Defaults seguros para
    # garantir backward compat com segmentar_materias.
    categoria: str | None = None
    manchete: str | None = None
    resumo: str | None = None
    valor_rs: float | None = None
    tags: list[str] = field(default_factory=list)
    relevante: bool = False


PADROES_MPRR: list[tuple[str, str]] = [
    # Famílias reais do MPRR (Ciclo 10.5a), validadas contra 3 edições reais
    # congeladas em tests/fixtures/ (2022-04-19, 2026-04-10, 2026-05-20).
    # O pymupdf4llm renderiza os cabeçalhos como blocos **bold** de linha
    # inteira; o hífen antes do "Nº" e o sufixo (PGJ/DG/DA/...) variam por
    # período, então casamos amplo por família (recall-first) e deixamos
    # filtrar/classificar decidirem relevância editorial. `(?m)` ancora no
    # início de cada linha — exclui menções inline e ruído (R E S O L V E,
    # assinaturas). Ver [[project_bug_padroes_mprr_markdown_real]].
    #
    # PORTARIA — atos (PGJ, DG, DA, instauração de PA/IC etc.):
    #   **PORTARIA - Nº 1136395 - PGJ, 19 DE MAIO DE 2026**
    #   **PORTARIA Nº 0493746 - PGJ, DE 18 DE ABRIL DE 2022**  (sem hífen)
    (r"(?m)^\*\*\s*PORTARIA\b[^\n*]*\*\*", "PORTARIA"),

    # EXTRATO — gasto e tramitação (nota de empenho, termo aditivo ao
    # contrato, da portaria de instauração/arquivamento/procedimento):
    #   **EXTRATO DE NOTA DE EMPENHO**
    #   **EXTRATO DO 2º TERMO ADITIVO AO CONTRATO Nº 36/2021 – ...**
    #   **EXTRATO DA PORTARIA DE ARQUIVAMENTO PA SIMP Nº ...**
    (r"(?m)^\*\*\s*EXTRATO\b[^\n*]*\*\*", "EXTRATO"),

    # AVISO — licitações:
    #   **AVISO DE LICITAÇÃO**  /  **AVISO DE REABERTURA DE LICITAÇÃO**
    (r"(?m)^\*\*\s*AVISO\b[^\n*]*\*\*", "AVISO"),
]

PADROES_TJRR: list[tuple[str, str]] = [
    (r"\*\*\s*EMENDA\s+REGIMENTAL\s+TJRR[^\n*]*\*\*", "EMENDA_REGIMENTAL"),
    (
        r"\*\*\s*PORTARIA\s+TJRR/\w+\s+N\.?\s*\d+[^\n*]*\*\*",
        "PORTARIA_ITEM",
    ),
    (r"\*\*\s*EXTRATO\s+DE\s+CONTRATO[^\n*]*\*\*", "EXTRATO_CONTRATO"),
]

ORGAOS_VALIDOS = {"MPRR", "TJRR"}


def segmentar_materias(
    markdown: str,
    orgao: str,
    pdf_url: str,
) -> list[Materia]:
    """Identifica matérias autônomas no Markdown e devolve lista de Materia.

    Estratégia: para cada padrão do órgão, encontra todas as ocorrências
    no Markdown via re.finditer (mantendo posições). Ordena por posição.
    Cada matéria vai do início do seu cabeçalho até o início da próxima
    matéria (ou fim do Markdown). Esse fatiamento por posição garante
    isolamento de texto entre matérias adjacentes.

    Validação de orgao acontece antes de tocar no Markdown — orgaos
    inválidos levantam ValueError sem trabalho desperdiçado.
    """
    if orgao not in ORGAOS_VALIDOS:
        raise ValueError(
            f"orgao inválido: {orgao!r}. Esperado: {ORGAOS_VALIDOS}"
        )

    if not markdown.strip():
        return []

    padroes = PADROES_MPRR if orgao == "MPRR" else PADROES_TJRR

    ocorrencias: list[tuple[int, str]] = []
    for padrao, tipo in padroes:
        for match in re.finditer(padrao, markdown, flags=re.IGNORECASE):
            ocorrencias.append((match.start(), tipo))

    if not ocorrencias:
        return []

    ocorrencias.sort(key=lambda x: x[0])

    materias: list[Materia] = []
    for i, (pos, tipo) in enumerate(ocorrencias):
        fim = ocorrencias[i + 1][0] if i + 1 < len(ocorrencias) else len(markdown)
        texto = markdown[pos:fim].strip()
        materias.append(
            Materia(orgao=orgao, tipo=tipo, texto=texto, pdf_url=pdf_url)
        )

    return materias
