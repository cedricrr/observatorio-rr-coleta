"""Filtro sensível por página — bloqueador da Sessão 12 (ECA art. 143).

Avalia o texto INTEGRAL de uma página de diário e decide se ela fica
fora do índice de busca. Aplicado no funil único do /indexar, então
sobrevive a reindexações por construção; a medição local
(scripts/medir_supressao.py no repositório do coletor) carrega ESTE
arquivo por caminho — manter o módulo puro e só-stdlib é contrato.

Só regras de ALTA PRECISÃO: o risco do art. 143 é a IDENTIFICABILIDADE
do menor, então cada regra exige contexto sensível + identificador.
Vocabulário amplo do validador editorial da Fase 3 (segredo de justiça,
medida protetiva, violência genérica) fica de fora de propósito — em
texto integral de diário de tribunal esses termos são rotina e
suprimiriam páginas legítimas em massa.

O PDF oficial e o texto/ no R2 permanecem intactos: a supressão cobre
só a camada de acesso por busca.
"""

from __future__ import annotations

import re
import unicodedata

REGRA_CRIME_SEXUAL = "crime_sexual_menor"
REGRA_IDADE = "idade_exata_menor"
REGRA_FAMILIA = "familia_iniciais"

# --- vocabulários (avaliados sobre texto normalizado: sem acento, casefold)
RE_CRIME_SEXUAL = re.compile(
    r"\b(estupro|abuso sexual|exploracao sexual|importunacao sexual)\b"
)
RE_PORNOGRAFIA_INFANTIL = re.compile(r"\bpornografia infantil\b")
RE_TERMO_MENOR = re.compile(
    r"\b(criancas?|adolescentes?|menor(es)? de idade|vulnera(vel|veis)|infantes?)\b"
)

# idade exata: termo inequívoco de menor a até 60 caracteres (mesma frase)
# de uma idade <= 17. "menor" isolado fica fora ("menor preço").
_MENOR_INEQUIVOCO = r"(criancas?|adolescentes?|menor(?:es)? de idade|recem-nascid\w*)"
_IDADE_ATE_17 = r"(?:1[0-7]|[1-9])\s+anos"
RE_IDADE_DEPOIS = re.compile(rf"\b{_MENOR_INEQUIVOCO}[^.\n]{{0,60}}?\b{_IDADE_ATE_17}\b")
RE_IDADE_ANTES = re.compile(rf"\b{_IDADE_ATE_17}\b[^.\n]{{0,60}}?\b{_MENOR_INEQUIVOCO}")

RE_FAMILIA = re.compile(
    r"\b(destituicao do poder familiar|acolhimento institucional)\b"
)

# iniciais anonimizadas, avaliadas sobre o texto ORIGINAL (case-sensitive):
# 2+ grupos "X." com conectivos opcionais ("J. da S. L.", "A. B. C.")
RE_INICIAIS = re.compile(
    r"\b[A-Z]\.(?:\s(?:d[aeo]s?\s)?[A-Z]\.)+"
)


def _normalizar(texto: str) -> str:
    sem_acento = (
        unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    )
    return sem_acento.casefold()


def pagina_sensivel(texto: str) -> str | None:
    """Nome da regra que casou, ou None se a página pode ser indexada."""
    if not texto:
        return None
    norm = _normalizar(texto)

    if RE_PORNOGRAFIA_INFANTIL.search(norm) or (
        RE_CRIME_SEXUAL.search(norm) and RE_TERMO_MENOR.search(norm)
    ):
        return REGRA_CRIME_SEXUAL

    if RE_IDADE_DEPOIS.search(norm) or RE_IDADE_ANTES.search(norm):
        return REGRA_IDADE

    if RE_FAMILIA.search(norm) and RE_INICIAIS.search(texto):
        return REGRA_FAMILIA

    return None
