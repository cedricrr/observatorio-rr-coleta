"""Validador determinístico de termos sensíveis — proteção a menores.

Fase 3 do incidente 2026-06-10 (ECA art. 143, Lei 8.069/90 — ver
docs/incidentes/2026-06-10-protecao-menores.md). Defesa em profundidade:
esta camada NÃO depende do RLM acertar — pega termos sensíveis por regex
mesmo se o classificador alucinar, ignorar o prompt ou mudar de
comportamento entre versões de modelo.

Chamado por scripts/jornal_diario.py DEPOIS de classificar e ANTES de
renderizar. Política fail-closed: na dúvida, despublica (falso positivo
custa uma matéria fora do jornal; falso negativo expõe um menor).

O matching é feito sobre texto SEM acentos (extração de PDF pode
perdê-los) e cobre texto, resumo, manchete e tags — superset do mínimo
(texto/resumo), porque qualquer campo renderizado pode expor a vítima.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from scripts.classificar import CATEGORIA_PROTECAO_MENOR
from scripts.segmentar import Materia

# Termos que indicam menor de idade sem ambiguidade. "menor" sozinho é
# armadilha ("menor preço" em licitações) — só conta qualificado.
_MENOR = r"(criancas?|adolescentes?|menor(es)?\s+de\s+idade|menor\s+[A-Z]\.)"

# Regras (nome, regex) avaliadas sobre texto sem acentos, IGNORECASE.
# Co-ocorrências usam lookaheads com (?s) para casar em qualquer ordem.
TERMOS_SENSIVEIS: list[tuple[str, str]] = [
    ("estupro", r"\bestupros?\b"),
    ("abuso sexual", r"\babusos?\s+sexua"),
    ("exploracao sexual", r"\bexploracao\s+sexual"),
    ("pornografia infantil", r"\bpornografia\s+infantil"),
    ("importunacao sexual", r"\bimportunacao\s+sexual"),
    # vulnerável/vulnerabilidade envolvendo criança/adolescente
    ("vulneravel + menor", rf"(?s)(?=.*\bvulnerab)(?=.*\b{_MENOR})"),
    # criança/adolescente com idade exata (identificabilidade)
    (
        "menor com idade exata",
        rf"\b{_MENOR}[^.\n]{{0,80}}?\b\d{{1,2}}\s+anos\b"
        rf"|\b\d{{1,2}}\s+anos\b[^.\n]{{0,80}}?\b{_MENOR}",
    ),
    # violência física contra menor
    (
        "violencia contra menor",
        rf"(?s)(?=.*\b(violencia|maus[\s-]tratos|agressao|lesao\s+corporal|"
        rf"castigos?\s+fisicos?))(?=.*\b{_MENOR})",
    ),
    # adoção/guarda envolvendo menor (co-ocorrência: "adoção de medidas"
    # e "guarda municipal" sozinhos não casam)
    ("adocao/guarda + menor", rf"(?s)(?=.*\b(adocao|guarda)\b)(?=.*\b{_MENOR})"),
    # destituição do poder familiar é inequívoca por si só
    ("destituicao de poder familiar", r"\bdestituicao\s+do?\s+poder\s+familiar"),
    ("segredo de justica", r"\bsegredo\s+de\s+justica"),
    # medida protetiva envolvendo menor
    ("medida protetiva + menor", rf"(?s)(?=.*\bmedidas?\s+protetivas?)(?=.*\b{_MENOR})"),
]

_REGRAS_COMPILADAS = [
    (nome, re.compile(padrao, re.IGNORECASE)) for nome, padrao in TERMOS_SENSIVEIS
]

# Iniciais anonimizadas pelo autor do diário ("J. da S. L.", "M. K."):
# duas ou mais iniciais maiúsculas com ponto, separadas por espaço,
# opcionalmente com conectivo (da/de/do/das/dos). CASE-SENSITIVE de
# propósito; exige espaço entre iniciais para não casar "S.A." de
# sociedades anônimas.
_RE_INICIAIS = re.compile(
    r"\b[A-Z]\.\s+(?:d[aeo]s?\s+)?[A-Z]\.(?:\s+(?:d[aeo]s?\s+)?[A-Z]\.)*"
)
NOME_REGRA_INICIAIS = "iniciais anonimizadas"


def _sem_acentos(texto: str) -> str:
    """Remove diacríticos preservando caixa (NFD → descarta combining)."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _campos_publicaveis(materia: Materia) -> str:
    """Concatena os campos que podem expor conteúdo sensível."""
    partes = [
        materia.texto or "",
        materia.resumo or "",
        materia.manchete or "",
        " ".join(materia.tags or []),
    ]
    return "\n".join(partes)


def casar_termo_sensivel(materia: Materia) -> str | None:
    """Retorna o nome da primeira regra sensível que casa, ou None.

    Avalia texto, resumo, manchete e tags da matéria, sem acentos.
    Exposto separadamente para a auditoria histórica (Fase 4) poder
    relatar QUAL termo casou sem aplicar o filtro.
    """
    alvo = _sem_acentos(_campos_publicaveis(materia))
    for nome, regra in _REGRAS_COMPILADAS:
        if regra.search(alvo):
            return nome
    if _RE_INICIAIS.search(alvo):
        return NOME_REGRA_INICIAIS
    return None


def aplicar_filtro_sensivel(materia: Materia) -> Materia:
    """Força relevante=False se texto contém termos sensíveis,
    independente do que o RLM classificou.

    Sem match, retorna a matéria inalterada. Com match, retorna nova
    Materia (função pura, via dataclasses.replace) com relevante=False,
    categoria sentinela e campos editoriais zerados — nada da matéria é
    renderizável. Idempotente: o texto bruto é preservado, então uma
    segunda aplicação casa de novo e produz o mesmo resultado.
    """
    if casar_termo_sensivel(materia) is None:
        return materia
    return replace(
        materia,
        relevante=False,
        categoria=CATEGORIA_PROTECAO_MENOR,
        manchete="",
        resumo="",
        valor_rs=None,
        tags=[],
    )
