# Incidente 2026-06-10 — Proteção a menores (ECA art. 143)

## Resumo

A home (`jornal/index.html`) exibia em destaque duas matérias da edição
MPRR de **2026-05-29** (ed. nº 971) sobre procedimentos administrativos da
Promotoria de Justiça da Comarca de Bonfim envolvendo adolescentes vítimas
de violência. A combinação de idade exata + município pequeno + número de
procedimento SIMP tornava as vítimas identificáveis, em violação ao
**art. 143 do ECA (Lei 8.069/90)**, que veda a divulgação de atos que
permitam identificar criança ou adolescente envolvido em procedimento
judicial ou policial.

Problema da mesma natureza já havia sido identificado em **17/05/2026**
(edição 2026-02-24), sem que a correção sistêmica fosse implementada à
época. Este documento registra a resposta ao incidente, em 4 fases.

Detalhes identificáveis (manchetes, resumos, números SIMP) ficam **fora
deste documento e fora do git** — estão na cópia de auditoria local
gitignored (`data/incidentes/`, ver Fase 1).

## Fase 1 — Emergência: despublicação imediata (2026-06-10)

Executada em 2026-06-10 ~22:38 (hora local, UTC-4) / 2026-06-11 02:38 UTC.

O que foi feito:

1. **Mapeamento da persistência**: as matérias publicadas vivem no sidecar
   JSON da edição no R2 (`jornal/2026-05-29.json`); a home agrega os 10
   sidecars mais recentes (`agregar_destaques_recentes`); o HTML da edição
   (`jornal/2026-05-29.html`) é renderizado das mesmas matérias. A página
   `jornal/diarios-mprr.html` contém apenas links de download dos PDFs,
   sem conteúdo de matérias.
2. **Novo script `scripts/despublicar_emergencia.py`**: remove do sidecar
   público as matérias cujo manchete/resumo/tags casam regex dados,
   re-renderiza o HTML da edição a partir do próprio sidecar (sem
   reprocessar via RLM) e regenera o índice da home. Antes de qualquer
   alteração grava cópia de auditoria (sidecar original + matérias
   removidas marcadas `relevante=False` + padrão que casou + timestamp)
   em `data/incidentes/` — diretório **gitignored** no mesmo commit
   (conteúdo despublicado não vai para git nem R2 público).
3. **Execução**: `--data 2026-05-29 --casar "estupro" --casar
   "adolescente"`. Dry-run confirmou exatamente 2 matérias casando (a
   terceira matéria da edição, contrato TJRR, não casou). Execução real
   republicou sidecar (`total_relevantes: 3 → 1`), HTML da edição e
   índice da home.
4. **Verificação via curl** (todas OK — nenhum termo sensível):
   - `jornal/index.html` — grep `estupro|adolescente.*Bonfim` → vazio.
   - `jornal/2026-05-29.html` — grep `estupro|adolescente|Bonfim|SIMP` → vazio.
   - `jornal/2026-05-29.json` — idem → vazio.
   - `jornal/diarios-mprr.html` — idem → vazio.
   - Sanidade: a matéria TJRR remanescente continua renderizada na edição.

Observações:

- O **PDF original do diário** permanece no arquivo R2 (`mprr/2026/05/...`)
  — é o documento oficial publicado pelo próprio MPRR; a política do
  projeto é arquivar a fonte primária integralmente. A despublicação
  cobre a camada **editorial** (manchete/resumo/destaque), que era o que
  amplificava a exposição.
- O cache do índice é `max-age=300`; a verificação foi feita após o
  upload e já retornou limpa.

## Fase 2 — Regra no classificador (prevenção sistêmica)

_Pendente — aguardando Gate 1._

## Fase 3 — Defesa em profundidade (validador independente)

_Pendente._

## Fase 4 — Reparação histórica

_Pendente._
