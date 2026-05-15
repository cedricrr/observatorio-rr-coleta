"""Filtro de matérias por sinais de descarte e inclusão forte."""

from __future__ import annotations

import re

from scripts.segmentar import Materia


SINAIS_DESCARTE: list[str] = [
    r"licença\s+para\s+tratamento\s+de\s+saúde",
    r"licença\s+maternidade",
    r"licença\s+por\s+motivo\s+de\s+doença",
    r"Convalidar\s+a\s+licença",
    r"Convalidar\s+a\s+designação",
    r"Convalidar\s+a\s+prorrogação",
    r"Convalidar\s+a\s+concessão\s+das\s+folgas",
    r"Conceder.*dias?\s+de\s+férias",
    r"Conceder\s+folgas?\s+compensatórias?",
    r"dia[s]?\s+de\s+folga,\s+em\s+razão\s+de\s+plantões",
    r"dispensa\s+do\s+serviço.*justiça\s+eleitoral",
    r"Cessar.*os\s+efeitos",
    r"Altera-se\s+o\s+CNPJ\s+da\s+empresa\s+matriz",
    r"sem\s+prejuízo\s+de\s+suas\s+atuais\s+atribuições",
]


SINAIS_INCLUSAO_FORTE: list[str] = [
    r"EXTRATO\s+DE\s+DISPENSA\s+DE\s+LICITAÇÃO",
    r"EXTRATO\s+D[OE]\s+CONTRATO",
    r"EXTRATO\s+DE\s+TERMO\s+ADITIVO",
    r"REMOVER,\s+a\s+pedido",
    r"EMENDA\s+REGIMENTAL",
    r"Apurar\s+suposta\s+prática",
    r"Apurar.*improbidade",
    r"Apurar.*desvio",
    r"Apurar\s+desmatamento",
    r"Apurar\s+a\s+regularidade",
    r"servidores\s+fantasmas",
    r"Prorrogar\s+a\s+cessão.*Senado",
    r"Prorrogar\s+a\s+cessão.*Câmara",
    r"CONCURSO\s+PÚBLICO\s+DE\s+PROVAS\s+E\s+TÍTULOS",
    r"DELEGAÇÕES\s+DE\s+SERVENTIAS",
    r"Lei\s+Antifacção",
    r"Lotar.*Cibersegurança",
]


TIPOS_SEMPRE_RELEVANTES: set[str] = {
    "ATO_PGJ",
    "EMENDA_REGIMENTAL",
    "DISPENSA_LICITACAO",
    "INSTAURACAO_IC",
}


_RE_DESCARTE = [re.compile(p, re.IGNORECASE) for p in SINAIS_DESCARTE]
_RE_INCLUSAO = [re.compile(p, re.IGNORECASE) for p in SINAIS_INCLUSAO_FORTE]


def _tem_descarte(texto: str) -> bool:
    """Verifica se algum SINAL_DESCARTE aparece no texto."""
    return any(p.search(texto) for p in _RE_DESCARTE)


def _tem_inclusao_forte(texto: str) -> bool:
    """Verifica se algum SINAL_INCLUSAO_FORTE aparece no texto."""
    return any(p.search(texto) for p in _RE_INCLUSAO)


def filtrar_materias(materias: list[Materia]) -> list[Materia]:
    """Filtra matérias por sinais de descarte e inclusão forte.

    Regras (em ordem de precedência):
    1. Sinal de descarte vence sempre — matéria com texto contendo
       qualquer SINAL_DESCARTE é descartada, mesmo se tipo for
       sempre relevante.
    2. Tipos em TIPOS_SEMPRE_RELEVANTES passam se não tiverem
       sinal de descarte.
    3. Outros tipos (EXTRATO_CONTRATO, PORTARIA_ITEM) precisam de
       SINAL_INCLUSAO_FORTE no texto para passar.
    4. Default conservador: tipo desconhecido ou sem sinal forte
       é descartado.

    Função pura: a lista de entrada não é modificada, uma nova
    lista é retornada.
    """
    resultado: list[Materia] = []
    for m in materias:
        if _tem_descarte(m.texto):
            continue
        if m.tipo in TIPOS_SEMPRE_RELEVANTES:
            resultado.append(m)
            continue
        if _tem_inclusao_forte(m.texto):
            resultado.append(m)
            continue
    return resultado
