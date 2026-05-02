"""Configuração estática das fontes monitoradas pelo coletor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fonte:
    """Define uma fonte de diários oficiais a ser monitorada."""

    codigo: str
    nome: str
    discovery_module: str


FONTES: list[Fonte] = [
    Fonte(
        codigo="mprr",
        nome="Ministério Público do Estado de Roraima",
        discovery_module="mprr",
    ),
    Fonte(
        codigo="tjrr",
        nome="Tribunal de Justiça do Estado de Roraima",
        discovery_module="tjrr",
    ),
]


def get_fonte(codigo: str) -> Fonte:
    """Retorna a Fonte com o código dado, ou levanta KeyError."""
    for f in FONTES:
        if f.codigo == codigo:
            return f
    raise KeyError(codigo)
