"""Classifica a sessão de busca do lead em 'tecnico' ou 'geral'.

Módulo puro (sem I/O): recebe os termos buscados na sessão e infere o
perfil do lead. Técnico = público jurídico/administrativo (advogados,
servidores, assessorias); geral = cidadão buscando o próprio nome ou
concursos. Empate resolve para técnico.

A comparação é sem acentos e case-insensitive — usuário de busca digita
"intimacao" tanto quanto "intimação" — e por palavra inteira, para
"citação" não casar dentro de "licitação".
"""

from __future__ import annotations

import re
import unicodedata

CLASSE_TECNICO = "tecnico"
CLASSE_GERAL = "geral"

RE_CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
RE_OAB = re.compile(r"\boab\b")
RE_PALAVRA = re.compile(r"[a-z]+")

VOCAB_PROCESSUAL = frozenset(
    {"intimacao", "acordao", "despacho", "sentenca", "citacao", "embargos"}
)
VOCAB_ADMINISTRATIVO = frozenset(
    {"portaria", "provimento", "resolucao", "designacao", "remocao"}
)
VOCAB_TECNICO = VOCAB_PROCESSUAL | VOCAB_ADMINISTRATIVO

# termos de concurso parecem nomes compostos ("concurso publico") mas são
# sinal de público geral — fora da contagem de nomes distintos
VOCAB_CONCURSO = frozenset({"concurso", "edital"})

MIN_NOMES_DISTINTOS = 3


def _normalizar(texto: str) -> str:
    sem_acento = (
        unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    )
    return sem_acento.casefold()


def _e_termo_tecnico(norm: str) -> bool:
    if RE_CNJ.search(norm):
        return True
    if RE_OAB.search(norm):
        return True
    return bool(set(RE_PALAVRA.findall(norm)) & VOCAB_TECNICO)


def _parece_nome(norm: str) -> bool:
    """Heurística: 2+ palavras alfabéticas, sem dígitos, sem vocabulário de concurso."""
    if any(c.isdigit() for c in norm):
        return False
    palavras = RE_PALAVRA.findall(norm)
    if len(palavras) < 2:
        return False
    return not set(palavras) & VOCAB_CONCURSO


def classificar_termos(termos: list[str]) -> str:
    """Classe do lead a partir dos termos buscados na sessão."""
    nomes_distintos: set[str] = set()
    for termo in termos:
        norm = _normalizar(termo)
        if _e_termo_tecnico(norm):
            return CLASSE_TECNICO
        if _parece_nome(norm):
            nomes_distintos.add(" ".join(RE_PALAVRA.findall(norm)))
    if len(nomes_distintos) >= MIN_NOMES_DISTINTOS:
        return CLASSE_TECNICO
    return CLASSE_GERAL
