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
    (r"\*\*\s*ATO\s+N\.?\s*\d+\s*-\s*PGJ\s*\*\*", "ATO_PGJ"),
    (r"\*\*\s*EXTRATO\s+D[OE]\s+CONTRATO[^\n*]*\*\*", "EXTRATO_CONTRATO"),
    (
        r"\*\*\s*EXTRATO\s+DA\s+PORTARIA\s+DE\s+INSTAURAÇÃO\s+DE\s+IC"
        r"[^\n*]*\*\*",
        "INSTAURACAO_IC",
    ),
    (
        r"\*\*\s*EXTRATO\s+DE\s+DISPENSA\s+DE\s+LICITAÇÃO[^\n*]*\*\*",
        "DISPENSA_LICITACAO",
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
