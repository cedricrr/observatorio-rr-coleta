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

## Fase 2 — Regra no classificador (prevenção sistêmica) (2026-06-10)

O que foi feito em `scripts/classificar.py`:

1. **SYSTEM_PROMPT**: nova seção "REGRA DE PROTEÇÃO A MENORES —
   PRIORIDADE MÁXIMA" inserida **antes** da seção de categorias, com
   precedência explícita sobre os critérios editoriais (texto literal
   definido pelo editor). Cobre crimes sexuais contra menores, violência
   física, padrão de iniciais anonimizadas pelo MP, vítima identificável
   por idade + município pequeno, adoção/destituição/guarda com
   nome/iniciais do menor e segredo de justiça. Para esses casos o modelo
   é instruído a responder apenas `relevante=False` e
   `categoria="protecao_menor"`, sem gerar manchete/resumo/tags.
2. **Nova sentinela `CATEGORIA_PROTECAO_MENOR`** (fora de
   `CATEGORIAS_VALIDAS` — não é categoria editorial e nunca renderiza).
   Sem isso a validação rejeitaria a resposta da regra com `ValueError` e
   a matéria seria pulada sem registro estruturado.
3. **Endurecimento determinístico**: quando a resposta vem com
   `categoria="protecao_menor"`, o código força `relevante=False` e zera
   manchete/resumo/tags/valor mesmo que o modelo os tenha preenchido ou
   devolvido `relevante=true`.

Testes: novo "GRUPO G — Proteção a menores" em `tests/test_classificar.py`
(7 testes: os 5 cenários definidos no plano + posição/conteúdo da regra no
prompt + sentinela fora das categorias editoriais). Como o cliente é
mockado, o grupo valida o prompt e o contrato/endurecimento do pipeline —
a camada que não depende do RLM acertar é a Fase 3. Suíte completa verde
(531 passed) e ruff limpo.

Limite conhecido: a regra do prompt depende do modelo obedecer. A Fase 3
adiciona o validador determinístico independente do RLM.

## Fase 3 — Defesa em profundidade (validador independente) (2026-06-10)

Novo `scripts/validador_sensivel.py` — camada determinística que NÃO
depende do RLM acertar:

- `casar_termo_sensivel(materia) -> str | None`: avalia regras de regex
  sobre texto + resumo + manchete + tags (superset do mínimo texto/resumo
  — qualquer campo renderizável pode expor a vítima), em texto
  **normalizado sem acentos** (extração de PDF pode perdê-los) e
  case-insensitive. Retorna o nome da regra que casou (a Fase 4 usa isso
  no relatório).
- `aplicar_filtro_sensivel(materia) -> Materia`: com match, força
  `relevante=False`, `categoria="protecao_menor"` e zera
  manchete/resumo/tags/valor (função pura via `dataclasses.replace`,
  idempotente). Sem match, devolve a matéria inalterada.

Regras: estupro; abuso/exploração sexual; pornografia infantil;
importunação sexual; vulnerabilidade + criança/adolescente; menor com
idade exata; violência física contra menor; adoção/guarda + menor;
destituição do poder familiar; segredo de justiça; medida protetiva +
menor; iniciais anonimizadas ("J. da S. L.", case-sensitive, exige
espaço entre iniciais). Mitigações de falso positivo testadas: "menor
preço" (licitação), "adoção de medidas" (burocrês), "S.A." (sociedade
anônima), "contrato por 5 anos". Política fail-closed: na dúvida,
despublica.

Integração: chamado em `jornal_diario.processar_chave` DEPOIS de
`classificar_materia` e ANTES de qualquer renderização — funil comum dos
dois caminhos (diário e backfill de publicação). Loga warning quando
despublica.

Testes: `tests/test_validador_sensivel.py` (48 testes: 17 textos
sensíveis parametrizados ×2, campos além do texto, controles de falso
positivo, idempotência, pureza, robustez a acentos/caixa) + GRUPO F em
`tests/test_jornal_diario.py` (3 testes de integração com o validador
REAL rodando — classificador mockado devolvendo relevante=True não passa
matéria sensível). Suíte completa: 582 verdes, ruff limpo.

**Replay contra o incidente real**: aplicado às matérias da cópia de
auditoria de 2026-05-29, o validador casa as duas matérias despublicadas
("vulneravel + menor" e "estupro") e não toca o contrato TJRR da mesma
edição.

## Fase 4 — Reparação histórica (2026-06-11)

### Auditoria (somente leitura)

Novo `scripts/auditar_historico.py`: varre todos os sidecars publicados
no R2 (`jornal/AAAA-MM-DD.json` — fonte da verdade do que está no ar) e
aplica `casar_termo_sensivel` (Fase 3) a cada matéria. Resultado:
**268 edições / 883 matérias auditadas, 52 achados, 0 erros**. (O total
de diários coletados é maior — ~1,3 mil PDFs — mas só 268 edições têm
camada editorial publicada; o restante não tem o que despublicar.)
Relatório completo (com manchetes) em `data/incidentes/` (gitignored).

Análise dos 52: ~10 com menor vítima identificável ou crime sexual
(inclui o caso conhecido de 17/05, edição 2026-02-24); ~11 de menores em
contexto coletivo/política pública; ~31 falsos positivos para fins do
ECA na regra de iniciais (adultos investigados anonimizados pelo MP e
razões sociais com iniciais, verificado por amostragem).

### Decisão editorial (2026-06-11)

**Marcação conservadora em lote**: NÃO julgar caso a caso agora. Todas
as 52 saem do ar provisoriamente; o status default passa a ser "fora do
ar" enquanto consulta externa (jurídica e editorial) não classifica
individualmente. Racional: na dúvida, despublicar — reverter é trabalho
de minutos (snapshots completos); manter exposto não é reversível.

### Execução (`scripts/despublicar_lote.py`)

Dois estágios com gate de confirmação manual entre eles:

1. `--preparar` (nada sobe): valida o relatório (exatamente 52 achados),
   re-deriva os matches com o MESMO validador da auditoria e cruza com o
   relatório (qualquer discrepância aborta); grava snapshots por matéria
   (estado completo + `relevante=False` + `motivo_despublicacao=
   "fase4-conservadora-20260611"` + `data_despublicacao` + termo casado,
   com sha256 no manifest) e snapshots de rollback por edição (sidecar e
   HTML originais); monta sidecars novos e re-renderiza os HTMLs em
   staging local. Falha de render → aborta sem tocar o R2.
2. `--executar`: sobe o staging com **rollback automático** (re-upload
   dos originais) se qualquer upload falhar; regenera índice e páginas
   de diários; grava relatório de execução.

Nota de design: a matéria despublicada SAI do sidecar público (não fica
nele com `relevante=False`) — o sidecar é público e só contém relevantes
por contrato (`agregar_destaques_recentes` não checa o campo); mantê-la
ali manteria a exposição. O registro `relevante=False` + motivo + data
vive no snapshot local, nunca no R2.

Resultado: **52 matérias despublicadas em 39 edições; 81 arquivos
publicados** (39 sidecars + 39 HTMLs + index + 2 páginas de diários);
0 já estavam fora do ar; 0 erros; sem necessidade de rollback.

### Validação pós-publicação

Após ≥30s de propagação, curl em **5 edições amostradas aleatoriamente**
(2026-03-23, 2026-02-24, 2025-10-09, 2026-03-12, 2025-10-01): nenhuma
manchete despublicada visível — 5/5 limpas. Home validada com
`grep -iE "estupro|vulnerável|adolescente.*(11|12|13|14|15|16|17).*ano"`
→ vazio.

### Pendências após a Fase 4

- **Consulta externa** (advogado / colegas do MP) e decisão individual
  sobre cada uma das 52 — em especial os ~31 falsos positivos de
  iniciais (adultos/empresas) e os ~11 casos coletivos/política pública,
  que são candidatos a republicação. Republicar = restaurar a matéria do
  snapshot ao sidecar e re-renderizar (mesmo mecanismo, sentido inverso).
- **Refinar a regra de iniciais** do validador (Fase 3) para não casar
  razões sociais ("J. W. Serviços Ltda") — hoje ela suprime matérias
  legítimas de contratos/desmatamento no pipeline diário (fail-closed).
- **Camada de busca** (`texto/` no R2 + Solr): indexa texto integral dos
  PDFs e está fora do escopo das 4 fases — decidir se o filtro sensível
  se aplica.
