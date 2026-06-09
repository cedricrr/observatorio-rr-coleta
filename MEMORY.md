# MEMORY.md — Evolução do projeto

Registro versionado da evolução do **Observatório Roraima — Coleta**. Serve de memória de longo prazo do projeto para colaboradores: o *porquê* das decisões e a ordem em que as coisas foram construídas. Para *como operar* o código (comandos, arquitetura), veja [CLAUDE.md](./CLAUDE.md); para o histórico fino, o `git log`.

Convenção: ao concluir um marco relevante, acrescente uma linha na seção correspondente (data ISO + o que mudou + o porquê, se não for óbvio). Datas refletem os commits.

---

## Linha do tempo

### Fundação — coleta e armazenamento (2026-05-01 → 05-02)
- Cliente **Cloudflare R2** (S3-compatible) como armazenamento imutável dos PDFs.
- Adaptadores de descoberta por órgão: **TJRR** e **MPRR** (`fontes/`), com interface comum (`discover`, `list_year`).
- Registro estático de fontes (`scripts/config.py`) carregado dinamicamente via `importlib` — adicionar fonte = novo módulo + entrada em `FONTES`.
- Núcleo + CLI do coletor (`scripts/coletar.py`): descoberta → dedupe via R2 → download streaming com sha256 → upload → Wayback → metadata JSON versionada.

### Backfill histórico (2026-05-04 → 05-14)
- Motor de **backfill com checkpoint retomável** (`scripts/backfill.py`), modos *listing* (por ano) e *daily* (por intervalo).
- `fix` chave (05-07): checkpoint persiste **após cada item** e em `try/finally` — crashes não perdem progresso.
- Backfill priorizado concluído 100%: MPRR 2022–2026 e **TJRR 2021–2026** carregados (várias rodadas, ~2.000+ edições). Metadados commitados em `data/diarios/`.

### Pipeline editorial (2026-05-09 → 05-17)
Cadeia de estágios isolados e testáveis, do PDF ao HTML:
- `extrair_texto` / `pdf_para_markdown` (PyMuPDF) — PDF → texto/Markdown.
- `segmentar` — fatia o Markdown em `Materia` por regex, por órgão (recall-first).
- `filtrar` — heurística de descarte/inclusão antes de gastar API.
- `cliente_anthropic` + `classificar` — classificação editorial via Claude API, com schema e categorias validados.
- `renderizar` — HTML do jornal (Jinja2).
- `jornal_diario` — orquestrador ponta a ponta.
- **infra** (05-17): `rodar_jornal.sh` + agent **launchd** rodando o jornal 2x/dia localmente no Mac.

### Publicação no R2 (2026-05-18, Ciclo 9.4)
- `publicar.py`: sobe o jornal HTML e regenera o índice no R2. Link "Fonte (PDF)" por matéria.
- **Contexto:** GitHub Actions ficou bloqueado no repo (~05-17), então o agendamento diário passou a viver no launchd local (workaround do Ciclo 9.2).

### Robustez e correção (2026-05-24 → 06-02, Sessão 10)
- Idempotência: temperatura determinística na classificação (10.1); `Cache-Control` no índice contra CDN stale (10.2); notificação de falha via webhook no launchd (10.4).
- **Fix `PADROES_MPRR`** (10.5): os regex não casavam o Markdown real do MPRR; reescritos em 3 famílias validadas contra fixtures reais (`tests/fixtures/`).
- `processar_chave` (10.6): permite **publicar sem re-coletar** (backfill de publicação usa a chave R2 dos JSONs locais; re-discover de data antiga geraria jornal vazio).
- Robustez de rede (10.7): timeouts curtos + retries em `cliente_anthropic` e `r2_client` contra hang de socket TCP.

### Home WSJ-style com sidecars (2026-06-02, Sessão 11)
- **Sidecar JSON** por edição (`sidecar.py`): persiste as matérias relevantes ao lado do HTML, com `SCHEMA_VERSAO`, para a home agregar sem reprocessar PDFs.
- `backfill_sidecars` retro-popula edições já publicadas (parse do HTML via BeautifulSoup).
- `agregar_destaques_recentes` + `indice.html.j2` redesenhado: hero + grid de destaques estilo jornal, alimentados pelos sidecars mais recentes.

### Migração para GitHub Actions (2026-06-04)
- GitHub Actions **desbloqueado**; o pipeline diário completo (coleta + jornal + publicação) migrou do launchd local para `.github/workflows/coletar.yml`, cron 2x/dia (13:00 e 22:00 UTC = 09h/18h Roraima).
- Workflow de CI separado (`testes.yml`): ruff + pytest em push/PR.
- launchd local **desinstalado** (cópia do plist mantida em `infra/` como rollback).
- Pegadinha resolvida na migração: os secrets `R2_*` no GitHub estavam com whitespace embutido → boto3 dava `Invalid endpoint`; recadastrados limpos via stdin. `ANTHROPIC_API_KEY` adicionado aos secrets.
- Migração **validada end-to-end** em 2026-06-08 (diário real: coleta + classificação via API + publicação + commit/push do bot). Actions atualizadas para Node 24 (checkout v6, setup-python v6, cache v5).

### Páginas de download de diários por órgão (2026-06-09)
- A home (`index.html`) perdeu a lista "Edições anteriores"; no lugar, dois links para páginas standalone de download: **`jornal/diarios-mprr.html`** e **`jornal/diarios-tjrr.html`**.
- Cada página lista todas as edições do órgão agrupadas por ano (âncoras, sem JS), com link de download apontando para a cópia no R2 (`url_r2`); MPRR mostra "Edição nº", TJRR não.
- `scripts/publicar.py`: `enumerar_diarios_fonte`, `agrupar_diarios_por_ano`, `gerar_pagina_diarios`, `publicar_pagina_diarios`; template `diarios.html.j2`. Regeradas a cada publish (em `publicar_tudo` e `--apenas-indice`). Implementado via TDD estrito.

### Polimento de UI/UX do índice (2026-06-09)
Cinco correções no template da home (`indice.html.j2`) + filtros, via TDD estrito (um ciclo por problema):
- **Datas formatadas**: novo global Jinja `formatar_data` (`_formatar_data_abrev` em `renderizar.py`) converte ISO → `08 JUN 2026`; hero/cards não vazam mais ISO cru. Masthead segue no formato longo (`_formatar_data_pt_br`).
- **Coluna direita**: a `.lado-direito` (antes `<div>` vazio com `border-left` morto em ≥1024px) recebeu conteúdo útil (ver iteração abaixo).
- **Acessibilidade**: `<main id="conteudo">`, skip link e `:focus-visible` em links/botões.
- **Trava editorial**: hero e loops só renderizam itens com `publicar | default(true)` — defesa em profundidade contra item sensível que escape do classificador.
- **CSS**: `line-clamp` padrão ao lado de `-webkit-line-clamp`, clamp de 4 linhas na `.lede`, transições de cor no hover.

**Iteração da coluna direita (mesmo dia):** a 1ª tentativa preencheu a `.lado-direito` com um índice "Nesta edição" (manchetes dos destaques), mas ficou **redundante** com os cards. Substituída por **ilustração SVG temática inline** (`_ilustracao_categoria` em `renderizar.py`, global `ilustracao_categoria`): 9 motivos line-art escolhidos pela `categoria` do hero (contratos→R$, pessoal→figuras, investigação→lupa, atos→§, designação→medalha, concurso→checklist, cessão→setas, judicial→balança, outros→jornal) com cor de acento por órgão (MPRR vermelho `#c8102e`, TJRR azul `#1d4e89`). Determinística, sem dependências novas (`Markup` do markupsafe), acompanha o hero a cada publicação.

---

## Princípios que se mantêm

- **Coleta não faz triagem** — baixa tudo; relevância é decidida só no pipeline editorial (independência editorial).
- **Fonte da verdade do dedupe é o R2** (`r2.existe()`), não o JSON local.
- **O git versiona só metadata imutável**; estado de execução (checkpoints, `/tmp`, logs) é gitignored.
- **Formatos são contrato**: `item_id` do backfill, chaves R2, schema do sidecar — mudanças exigem cuidado com retrocompatibilidade.
