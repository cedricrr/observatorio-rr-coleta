# Sessão 13 · Ciclo 13.0 — Estado atual da busca e do funil

Levantamento de 2026-06-12, lido do código em `main` (commit `654bb53`). Base factual dos
ciclos 13.1–13.6; qualquer suposição do plano que contradisser este documento perde.

## API de busca (`search/api`, FastAPI no Railway)

Subprojeto com venv e pyproject próprios (deps não entram no venv do coletor). Produção:
`https://api-production-160d.up.railway.app` (projeto Railway `observatorio-busca`), Solr 9
privado (IPv6 only) + Postgres no mesmo projeto. Testes: `cd search/api && .venv/bin/python -m pytest`.

Config (`app/config.py`) — todas obrigatórias, falha no boot se ausentes:
`SOLR_URL`, `DATABASE_URL`, `SEARCH_API_TOKEN`, `SESSION_SECRET`, `CORS_ALLOWED_ORIGINS`
(lista separada por vírgula), `R2_PUBLIC_DOMAIN`.

CORS (`app/main.py`): origens da env, métodos GET/POST, headers `X-Sessao` e `Content-Type`.
Rate limit (`app/limites.py`, slowapi por IP, primeiro hop do `X-Forwarded-For`):
`/buscar` 30/min, `/leads` 5/min; `/indexar` isento (autenticado).

### `POST /buscar` (freemium — o gate de 3 já é servidor)

Body: `{ q: str (1..200, não vazio), offset: int >= 0 }`.
Sem `X-Sessao`: resposta **parcial** — 3 diários mais recentes + contagens reais.
Com `X-Sessao` válido: lista completa, paginada em 20 (`offset`). Header presente mas
inválido/expirado → **401** (o frontend limpa o token e refaz como anônimo).

Solr: edismax sobre `texto`, **`mm=100%`** (todos os termos obrigatórios), grouping por
`chave_pdf` (1 resultado por diário, primeira página com match), highlight, ordenado por
`data_edicao desc`.

Resposta: `{ total_diarios, total_ocorrencias, parcial: bool, resultados: [...] }`;
cada resultado: `orgao`, `data_edicao`, `numero`, `pagina`, `trecho_html` (já escapado,
só `<em>` de highlight), `url_pdf`. Erro do Solr → 502 sem vazar URL interna.

### `POST /leads` (estado que o Ciclo 13.1 evolui)

Body atual: `{ email: EmailStr, telefone?: str(<=40), consentimento: bool, origem_busca?: str(<=200) }`.
`consentimento != true` → 400. Resposta: `{ token }`.
**Não existem hoje**: nome, consentimento granular (2 checkboxes), classificador de classe,
`termos_sessao` (só o último termo em `origem_busca`), `ip_hash`, normalização E.164.

Persistência (`app/db.py`, psycopg3 sem ORM, conexão por request): DDL inline
`CREATE TABLE IF NOT EXISTS` rodado na própria conexão do insert — **não há ferramenta de
migração**; colunas novas entram como `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` no mesmo
estilo. Tabela `leads`: `id, email (unique em lower(email)), telefone, consentimento_em,
finalidade, origem_busca, criado_em`. Upsert por e-mail: renova consentimento, telefone só
sobrescreve se veio preenchido — a idempotência pedida no plano **já existe**.

### Token de sessão (`app/sessao.py`)

itsdangerous `URLSafeTimedSerializer`, salt `sessao-busca-v1`, validade **180 dias**, payload
`{"v": 1}` sem PII. Não é autenticação: é o gate de lead capture. Vai em `localStorage`
(chave `obs_busca_token`) + header `X-Sessao` — sem cookies.

### `POST /indexar`

Único endpoint autenticado (`Authorization: Bearer SEARCH_API_TOKEN`, comparação constante).
Recebe o documento `texto/` (schema `versao: 1`), explode 1 doc Solr por página
(`id = {chave_pdf}#{pagina}`) e envia. É o **funil único** de entrada do índice — chamado por
`scripts/indexar_diaria.py` (3 jobs do Actions) e `scripts/backfill_indexacao.py` (carga
histórica). Ponto de aplicação natural do filtro de supressão (bloqueador da Sessão 12,
`docs/sessao-12/plano.md`). Resposta: `{ "indexadas": N }`.

### `GET /health`

Ping no Solr e no Postgres.

## Acervo indexado

2.226 edições / ~92,5k páginas (carga completa validada 2026-06-11). O índice é **derivado e
reconstruível** de `texto/` no R2; o Solr nunca é exposto. PDFs escaneados sem camada de texto
aparecem como `paginas_vazias` no `texto/` (OCR fora de escopo).

## Frontend

### `scripts/templates/busca.html.j2`

Página estática com JS vanilla (sem framework, sem build JS). `var API = "{{ busca_api_url }}"`
injetado no render. Fluxo: `POST {API}/buscar` com `{q, offset}`; `X-Sessao` se houver token;
em 401 limpa token e refaz como anônimo; resposta `parcial` mostra o **gate inline**
(`#form-cadastro`: e-mail, telefone, 1 checkbox) que posta em `{API}/leads`, grava o token e
refaz a busca; com sessão, botão "Carregar mais" pagina de 20 em 20. Único `innerHTML` da
página é o `trecho_html` (contrato: API entrega escapado).

O Ciclo 13.4 **substitui o gate inline** por placeholders sob blur + página `cadastro.html`
exclusiva; o resto do fluxo (token, 401, paginação) permanece.

### Demais templates (`scripts/templates/`)

`indice.html.j2` (home, com painel de estatísticas do acervo condicional à busca),
`jornal.html.j2` (edição), `diarios.html.j2` (páginas por órgão), `sobre.html.j2`,
`busca.html.j2`. Cada template define o próprio `:root` CSS com a paleta antiga
(`#c8102e` etc.) — alvo do Ciclo 13.5. Tipografia: Fraunces, Inter, JetBrains Mono.
Beacon do Cloudflare Web Analytics condicional a `CF_ANALYTICS_TOKEN` (padrão a seguir
para condicionais de env).

## Build e publicação

`scripts/publicar.py`: renderiza e sobe ao R2. `SEARCH_API_URL` (env, opcional) é lida em um
ponto único e injetada como `busca_api_url`; **sem ela, a página de busca e o painel da home
não são emitidos** — convenção a manter nos módulos novos. Cache: páginas mutáveis
(índice, diários, sobre) `max-age=300`; robots/sitemap `max-age=3600`; HTMLs/sidecars de
edição imutáveis. Deploy do frontend = job `publicacao` do Actions (ou `workflow_dispatch`);
deploy da API = `railway up` de dentro de `search/api` (diretório linkado é a raiz de build).

## Implicações para os ciclos

1. **13.1**: contrato novo de `/leads` quebra o frontend antigo → deploy da API e publish do
   frontend na mesma janela (cache de 5 min). DDL novo aplica sozinho no primeiro request.
2. **13.2**: `POST /eventos` segue o padrão de `limites.py` (rate limit próprio) e o modelo
   Pydantic deve proibir campos extras (evento é pré-consentimento, sem dado pessoal).
3. **13.3/13.4**: testes de template em pytest no venv do coletor (renderizar e inspecionar o
   HTML), padrão dos testes existentes; não há toolchain JS — comportamento de página testável
   só pelo HTML/atributos gerados, a lógica JS é validada no checklist manual do 13.6.
4. **13.5**: paleta é duplicada por template; aplicar via bloco/include comum ou replicar com
   consistência — decidir no ciclo.
5. Supressão no índice: bloqueador do cutover, planejado em `docs/sessao-12/plano.md`.
