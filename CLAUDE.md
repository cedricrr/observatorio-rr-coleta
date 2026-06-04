# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Coletor de diários oficiais do **Observatório Roraima** (projeto cívico independente). Baixa diários do **MPRR** (Ministério Público de Roraima) e **TJRR** (Tribunal de Justiça de Roraima), armazena os PDFs no **Cloudflare R2** (arquivo imutável) e versiona metadados JSON neste git (histórico auditável). Sobre isso há um pipeline editorial que classifica matérias via Claude API e publica um jornal HTML + índice no R2.

Política editorial: a **coleta** não faz triagem (baixa tudo). A **classificação/relevância** é decidida no pipeline editorial. Toda saída pública vai pro R2; o git guarda só metadados imutáveis.

## Comandos

```bash
# Ambiente (Python >=3.10)
.venv/bin/python -m pip install -e ".[dev]"

# Testes (pytest configurado em pyproject.toml, testpaths=["tests"])
.venv/bin/python -m pytest                              # suíte completa (22 arquivos)
.venv/bin/python -m pytest tests/test_coletar.py        # um arquivo
.venv/bin/python -m pytest tests/test_coletar.py::test_nome -v   # um teste
.venv/bin/python -m pytest -k "backfill"                # por expressão

# Lint (ruff, line-length=100)
.venv/bin/ruff check .

# Coleta de um dia (descobre, baixa, sobe ao R2, grava metadata)
.venv/bin/python -m scripts.coletar --data hoje --fonte todas
.venv/bin/python -m scripts.coletar --data 2026-06-03 --fonte mprr

# Jornal editorial (coleta inline + classifica + renderiza HTML + sidecar)
.venv/bin/python -m scripts.jornal_diario --data hoje --fonte todas

# Publicar jornal e regenerar índice no R2
.venv/bin/python -m scripts.publicar --data hoje
.venv/bin/python -m scripts.publicar --apenas-indice

# Backfill histórico (ver "Backfill" abaixo)
.venv/bin/python -m scripts.backfill --fonte mprr --anos 2024,2023 --retomar
.venv/bin/python -m scripts.backfill --fonte tjrr --de 2024-01-01 --ate 2024-12-31 --somente-dias-uteis
```

Todos os scripts são módulos executáveis (`python -m scripts.<nome>`), não arquivos soltos — o pacote é importado como `scripts.*` e `fontes.*` (ver `[tool.setuptools.packages.find]`).

## Arquitetura

Dois pacotes: **`fontes/`** (adaptadores por órgão) e **`scripts/`** (core + orquestração). A separação central é **descoberta** (específica por fonte) vs **pipeline** (genérico).

### Fontes (`fontes/mprr.py`, `fontes/tjrr.py`)

Cada fonte é um módulo com uma interface comum, carregada dinamicamente via `importlib.import_module(f"fontes.{discovery_module}")` a partir de `scripts/config.py` (`FONTES`, dataclass `Fonte`). Contrato:

- `discover(data_alvo: date) -> dict | None` — acha a edição de uma data. `None` = sem diário.
- `list_year(year: int) -> list[dict]` — lista todas as edições de um ano (modo backfill listing; só MPRR implementa hoje).
- Cada "descoberta" é um `dict` com chaves **`url`**, **`data_edicao`** (ISO), e opcional **`numero`** (edição). Esse formato é um **contrato**: o core depende dessas chaves.

Diferenças importantes entre fontes:
- **MPRR** tem `numero` de edição (várias por dia possíveis) e usa CSRF/sessão; **TJRR** é uma edição por data, sem número. A chave R2 e o nome do JSON ganham sufixo `-<numero>` só quando há número.
- **Throughput muito assimétrico**: TJRR ~98s/data, MPRR ~8s/edição (~12x). Planeje janelas de TJRR com folga.

### Pipeline de coleta (`scripts/coletar.py`)

`main` → `processar_fonte` (chama `discover`) → `processar_descoberta`:
1. `montar_chave_r2` → `r2.existe(chave)` para **dedupe** (a fonte da verdade do dedupe é o R2, NÃO o JSON local).
2. `baixar_pdf` em streaming para `/tmp`, calculando sha256.
3. `r2.upload` com metadata `{"sha256", "data-edicao"}`.
4. `submeter_wayback` (best-effort, nunca quebra a coleta).
5. `gravar_metadados` → `data/diarios/<orgao>/<data>[-<numero>].json`.

### Pipeline editorial (`scripts/jornal_diario.py` orquestra)

Estágios, cada um um módulo testável isoladamente:
1. `baixar_pdf.baixar_pdf_do_r2` — busca o PDF do R2 por chave.
2. `pdf_para_markdown.pdf_para_markdown` (via `pymupdf4llm`) — PDF→Markdown.
3. `segmentar.segmentar_materias` — fatia o Markdown em `Materia` por regex (`PADROES_MPRR`/`PADROES_TJRR`). Recall-first: casa amplo, deixa filtrar/classificar decidir.
4. `filtrar.filtrar_materias` — heurística de descarte/inclusão (`SINAIS_DESCARTE`/`SINAIS_INCLUSAO_FORTE`) antes de gastar API.
5. `classificar.classificar_materia` — chama a Claude API; valida JSON contra `CATEGORIAS_VALIDAS` e schema obrigatório; retorna nova `Materia` (função pura via `dataclasses.replace`).
6. `renderizar.renderizar_jornal` — Jinja2 (`scripts/templates/jornal.html.j2`).
7. `sidecar.montar_sidecar` — JSON de matérias relevantes salvo ao lado do HTML, consumido depois por `publicar` sem reprocessar.

Resiliência por estágio: falha de pipeline → `[]`; falha de classificação de UMA matéria → pula só ela.

Há **dois caminhos** no orquestrador:
- `_processar_fonte` (diário): coleta inline com `discover` então processa.
- `processar_chave` (backfill de publicação): recebe a chave R2 direto dos JSONs locais e **não re-descobre** — discover de data antiga pode falhar e gerar jornal vazio mesmo com o PDF já no R2.

### Publicação (`scripts/publicar.py`)

`publicar_tudo`: sobe `jornal/<data>.html` → `jornal/<data>.json` (sidecar) → regenera `jornal/index.html`. O índice tem `Cache-Control: max-age=300` (muda a cada publicação); HTMLs/sidecars de edição são imutáveis e sobem sem Cache-Control. `agregar_destaques_recentes` baixa os N sidecars mais recentes e monta hero + grid da home.

### R2 (`scripts/r2_client.py`)

`R2Client.from_env()` lê 5 vars `R2_*` do `.env`. boto3 com endpoint Cloudflare, retries adaptativos. Métodos: `existe`, `upload`, `url_publica`, `download_bytes`.

### Cliente Anthropic (`scripts/cliente_anthropic.py`)

`ClienteAnthropic` encapsula a SDK. Default model `claude-sonnet-4-6`. **Pegadinha**: com `extended_thinking=True` a API exige `temperature=1`, então `temperature` só é enviado quando thinking está desligado. O orquestrador usa `extended_thinking=False`.

## Backfill (`scripts/backfill.py`)

Reprocessa histórico com **checkpoint retomável** em `data/backfill/<escopo>.json` (gitignored). Dois modos mutuamente exclusivos:
- **listing** (`--anos`): usa `list_year` da fonte.
- **daily** (`--de`/`--ate`, opcional `--somente-dias-uteis`): itera datas.

Convenções que são contrato:
- `item_id`: `<codigo>-<data>-<numero>` (listing) ou `<codigo>-<data>` (daily). Versionado — não mude o formato.
- `STATUS_VALIDOS = {"sucesso", "erro", "pulado_dedupe", "sem_diario"}`. `--dry-run` reusa `pulado_dedupe`.
- O checkpoint persiste após cada item e em `try/finally` — crashes preservam progresso; `--retomar` continua.

`--somente-dias-uteis` só pula sáb/dom — **não conhece feriados** nem recesso forense (jul–ago pode ser ~5 semanas sem diário no TJRR).

## Convenções e armadilhas

- **Datas**: sempre use `data_edicao`/`start` como fonte da data. No MPRR algumas edições têm **ano errado no título** — nunca derive a data do título.
- **Assimetria de chaves de metadata**: os JSONs em `data/diarios/` usam `data_edicao` (underscore), mas a metadata custom no upload R2 usa **`data-edicao` (hífen)** — exigência do R2. Intencional; não "uniformize".
- **JSON local ≠ PDF no R2**: a existência de um JSON em `data/diarios/` NÃO garante o PDF no R2. Dedupe sempre via `r2.existe()`.
- **Estado de execução fora do git**: `/tmp/`, `/data/backfill/`, `*.log`, `refs/` são gitignored. O git versiona só metadata final imutável. Qualquer pasta dinâmica nova deve entrar no `.gitignore` no MESMO commit.
- **Testes com `mock.patch` + `importlib`**: o patch de `importlib.import_module` precisa ser o **último** decorator/context, senão patches subsequentes falham silenciosamente.
- As fixtures em `tests/fixtures/` são Markdown real congelado de edições MPRR/TJRR — os regex de `segmentar.py` são validados contra elas; ao mexer nos padrões, rode `test_segmentar.py`.

## Automação (`infra/`, `scripts/rodar_jornal.sh`)

launchd roda `rodar_jornal.sh` 2x/dia (09:00 e 18:00) via `com.observatoriorr.jornal.plist`. O wrapper roda `jornal_diario` e, se exit==0, `publicar`. launchd **não injeta env vars** — o `WEBHOOK_URL` (notificação de falha opcional) é lido grepando o `.env`. GitHub Actions está bloqueado no repo (ticket aberto); a automação vive nesse cron local no Mac.
