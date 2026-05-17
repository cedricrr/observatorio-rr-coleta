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
    # PORTARIA PGJ — formato real do MPRR:
    # **PORTARIA - Nº 1125662 - PGJ, 29 DE ABRIL DE 2026**
    # 21 ocorrências/edição em média. Hífens podem ser '-' OU '–'.
    (
        r"\*\*\s*PORTARIA\s*[-–]\s*Nº\s*\d+\s*[-–]\s*PGJ[^\n*]*\*\*",
        "PORTARIA_PGJ",
    ),

    # PORTARIA DE INSTAURAÇÃO — formato real (título pode estar
    # quebrado em 2 blocos ** consecutivos pelo pymupdf4llm):
    # **PORTARIA Nº 022/2026 – MP/PJ/SLA – DE INSTAURAÇÃO DO PA Nº ...**
    # Regex casa apenas o primeiro bloco com a palavra INSTAURAÇÃO.
    (
        r"\*\*\s*PORTARIA\s+Nº\s*\d+[^\n*]*INSTAURAÇÃO[^\n*]*\*\*",
        "INSTAURACAO_IC",
    ),

    # EXTRATO DO CONTRATO — formato real dentro de tabela Markdown,
    # SEM cercadura **, com <br> separando linhas:
    # ...<br>EXTRATO DO CONTRATO Nº 34/2026 – PROCESSO ...<br>...
    # Padrão para no <br> ou \n para isolar só o título.
    (
        r"EXTRATO\s+D[OE]\s+CONTRATO\s+Nº?\s*\d+[^\n<]*",
        "EXTRATO_CONTRATO",
    ),

    # EXTRATO DE DISPENSA DE LICITAÇÃO — similar (tabela, sem **).
    (
        r"EXTRATO\s+DE\s+DISPENSA\s+DE\s+LICITAÇÃO[^\n<]*",
        "DISPENSA_LICITACAO",
    ),

    # EXTRATO DE TERMO ADITIVO — tipo novo descoberto no refactor.
    # Mesma estrutura de tabela.
    (
        r"EXTRATO\s+DE\s+TERMO\s+ADITIVO[^\n<]*",
        "TERMO_ADITIVO",
    ),
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
