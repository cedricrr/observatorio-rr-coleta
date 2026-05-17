"""Classificação editorial de matérias via RLM."""

from __future__ import annotations

import json
from dataclasses import replace

from scripts.cliente_anthropic import ClienteAnthropic
from scripts.segmentar import Materia


CATEGORIAS_VALIDAS: frozenset[str] = frozenset({
    "Contratos e licitações",
    "Movimentação de pessoal",
    "Investigações e inquéritos",
    "Atos normativos",
    "Designações e nomeações",
    "Concursos e delegações",
    "Cessões e cooperações",
    "Decisões judiciais relevantes",
    "Outros",
})


SYSTEM_PROMPT = """Você é o classificador editorial do Observatório Roraima.

O Observatório Roraima é uma plataforma cívica que monitora os diários
oficiais do Ministério Público (MPRR) e do Tribunal de Justiça (TJRR)
do estado de Roraima, identificando matérias com interesse jornalístico
e cívico para a população local.

Sua tarefa é classificar uma matéria isolada de um diário oficial,
extraindo informações estruturadas para publicação editorial.

CATEGORIAS DISPONÍVEIS (escolha exatamente uma):

1. "Contratos e licitações" — extratos de contrato, dispensas de
   licitação, pregões, termos aditivos. Aquisições de bens ou serviços.
2. "Movimentação de pessoal" — remoções, promoções, lotações,
   transferências, exonerações. Inclui ATO_PGJ típicos.
3. "Investigações e inquéritos" — instauração de IC, apurações de
   improbidade, procedimentos investigatórios.
4. "Atos normativos" — emendas regimentais, portarias normativas,
   resoluções, instruções. Mudanças nas regras institucionais.
5. "Designações e nomeações" — designações para função de confiança,
   nomeações para cargo comissionado, posses.
6. "Concursos e delegações" — abertura de concurso público, edital,
   homologação de cartórios, delegação de serventias.
7. "Cessões e cooperações" — cessão de servidor entre órgãos,
   acordos de cooperação técnica.
8. "Decisões judiciais relevantes" — sentenças e acórdãos do TJRR
   com repercussão pública. Use com parcimônia.
9. "Outros" — fallback quando nenhuma categoria acima se encaixa.

CRITÉRIO DE RELEVÂNCIA EDITORIAL:

Uma matéria é RELEVANTE quando interessa ao cidadão comum por:
- Envolver gasto público significativo (R$ acima de R$ 30 mil)
- Movimentar cúpula institucional (procuradores, desembargadores)
- Estabelecer mudança normativa
- Apurar irregularidade
- Abrir oportunidade pública (concurso, edital)

Marque relevante=False quando a matéria for de rotina administrativa
sem repercussão pública (designações temporárias, ferias, etc).

SCHEMA OBRIGATÓRIO da resposta:

{
  "relevante": bool,
  "categoria": "<uma das 9 strings acima>",
  "manchete": "<frase curta, 60-100 chars>",
  "resumo": "<2-4 frases, 200-500 chars>",
  "valor_rs": <número ou null>,
  "tags": ["<2-5 palavras-chave>"]
}

REGRAS ABSOLUTAS:

- Responda APENAS com JSON válido, sem texto antes ou depois.
- Categoria deve ser EXATAMENTE uma das 9 strings listadas.
- valor_rs deve ser número (não string) ou null.
- Tags em lista de strings, sem duplicatas.
- Manchete e resumo em português brasileiro, terceira pessoa,
  tom jornalístico neutro.
"""


def _montar_user_prompt(materia: Materia) -> str:
    """Formata texto da matéria e metadados como user prompt."""
    return f"""ÓRGÃO: {materia.orgao}
TIPO IDENTIFICADO: {materia.tipo}

MATÉRIA (Markdown):
---
{materia.texto}
---

Classifique editorialmente segundo as instruções do sistema.
Responda APENAS com JSON válido no formato esperado, sem texto antes
ou depois."""


def _strip_markdown_fence(texto: str) -> str:
    """Remove markdown code fence se presente.

    O modelo Claude frequentemente envolve respostas JSON em fence
    ```json...``` mesmo quando instruído a retornar apenas JSON.
    Esta função remove fence envolvente para tornar a string
    parseável por json.loads.

    Idempotente: string sem fence é retornada inalterada (após
    strip de whitespace).

    Casa variações: "```json", "```", " ``` json " com/sem
    whitespace ao redor.
    """
    texto = texto.strip()
    if not texto.startswith("```"):
        return texto

    primeira_quebra = texto.find("\n")
    if primeira_quebra == -1:
        return texto.lstrip("`").strip()

    texto = texto[primeira_quebra + 1:]

    if texto.endswith("```"):
        texto = texto[:-3]

    return texto.strip()


def _parsear_resposta_json(texto: str) -> dict:
    """Parseia JSON da resposta. Levanta ValueError se inválido.

    Tolera respostas envoltas em markdown code fence (```json...```)
    — comportamento comum do modelo Claude apesar do system prompt
    pedir o contrário.
    """
    texto_limpo = _strip_markdown_fence(texto)
    try:
        dados = json.loads(texto_limpo)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido na resposta do RLM: {e}") from e
    if not isinstance(dados, dict):
        raise ValueError("JSON da resposta não é um objeto")
    return dados


def _validar_dados_classificacao(dados: dict) -> None:
    """Valida que dados têm todos os campos obrigatórios e tipos corretos.

    Levanta ValueError em qualquer falha. Mensagem identifica o campo
    problemático para facilitar debug.
    """
    obrigatorios = {
        "relevante": bool,
        "categoria": str,
        "manchete": str,
        "resumo": str,
        "tags": list,
    }
    for campo, tipo_esperado in obrigatorios.items():
        if campo not in dados:
            raise ValueError(f"Campo obrigatório '{campo}' ausente")
        if not isinstance(dados[campo], tipo_esperado):
            raise ValueError(
                f"Campo '{campo}' deve ser {tipo_esperado.__name__}, "
                f"recebido {type(dados[campo]).__name__}"
            )

    if "valor_rs" not in dados:
        raise ValueError("Campo obrigatório 'valor_rs' ausente")
    valor = dados["valor_rs"]
    if valor is not None and not isinstance(valor, (int, float)):
        raise ValueError(
            f"Campo 'valor_rs' deve ser número ou null, "
            f"recebido {type(valor).__name__}"
        )

    if dados["categoria"] not in CATEGORIAS_VALIDAS:
        raise ValueError(
            f"categoria '{dados['categoria']}' não está nas categorias "
            f"válidas: {sorted(CATEGORIAS_VALIDAS)}"
        )

    for i, tag in enumerate(dados["tags"]):
        if not isinstance(tag, str):
            raise ValueError(
                f"Tag [{i}] deve ser str, recebido {type(tag).__name__}"
            )


def classificar_materia(
    materia: Materia,
    cliente: ClienteAnthropic,
) -> Materia:
    """Classifica uma matéria via RLM e retorna nova Materia preenchida.

    Função pura: a Materia de entrada não é modificada. Uma nova
    instância é retornada via dataclasses.replace com os campos
    editoriais preenchidos pelo RLM.

    Validações fortes na resposta do RLM:
    - JSON deve ser válido
    - Todos os campos obrigatórios devem estar presentes
    - Tipos devem casar (relevante=bool, manchete=str, etc)
    - Categoria deve estar nas 9 CATEGORIAS_VALIDAS

    Qualquer falha levanta ValueError com mensagem identificando o
    problema. Exceções da API (rate limit, timeout) propagam do
    cliente sem captura.
    """
    user_prompt = _montar_user_prompt(materia)
    resposta = cliente.classificar(user_prompt, system=SYSTEM_PROMPT)
    dados = _parsear_resposta_json(resposta)
    _validar_dados_classificacao(dados)

    return replace(
        materia,
        relevante=dados["relevante"],
        categoria=dados["categoria"],
        manchete=dados["manchete"],
        resumo=dados["resumo"],
        valor_rs=dados["valor_rs"],
        tags=list(dados["tags"]),
    )
