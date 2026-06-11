# Busca textual — Observatório Roraima

Serviço de busca nos diários (MPRR/TJRR) com captura de leads. Três
componentes: **Solr** (índice, privado), **API FastAPI** (único serviço
público) e **Postgres** (leads — PII fica só aqui).

O índice é **derivado e 100% reconstruível** a partir do cache de texto
no R2 (`texto/…json`, gerado por `scripts/cache_texto.py` no repo raiz).
Perder o volume do Solr não perde dado nenhum: re-rodar o backfill de
indexação reconstrói tudo.

## Desenvolvimento local

```bash
cd search/
docker compose up --build
# API:  http://localhost:8080  (health: GET /health)
# Solr: http://localhost:8983  (admin, só local)

# Testes da API (venv própria, não usa o venv do coletor)
cd api/
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

Smoke manual com o stack de pé:

```bash
# indexa um documento de texto (schema versao=1)
curl -s http://localhost:8080/indexar \
  -H "Authorization: Bearer dev-token" -H "Content-Type: application/json" \
  -d @exemplo-texto.json

# busca aberta (parcial) e cadastro
curl -s http://localhost:8080/buscar -H "Content-Type: application/json" \
  -d '{"q": "João da Silva"}'
curl -s http://localhost:8080/leads -H "Content-Type: application/json" \
  -d '{"email": "x@example.com", "consentimento": true}'
# busca completa: repete /buscar com header X-Sessao: <token do /leads>
```

## Endpoints

| Rota | Auth | Função |
|---|---|---|
| `POST /buscar` | — (parcial) / `X-Sessao` (completa) | grouping por diário + trecho com highlight |
| `POST /leads` | — | cadastro com consentimento LGPD; devolve token de sessão |
| `POST /indexar` | `Authorization: Bearer SEARCH_API_TOKEN` | recebe doc de texto, indexa por página |
| `GET /health` | — | ping Solr + Postgres |

Rate limit por IP: `/buscar` 30/min, `/leads` 5/min.

## Env vars do serviço `api`

| Var | Exemplo |
|---|---|
| `SOLR_URL` | `http://solr.railway.internal:8983/solr/diarios` |
| `DATABASE_URL` | injetada pelo Railway (reference do plugin Postgres) |
| `SEARCH_API_TOKEN` | `openssl rand -hex 32` |
| `SESSION_SECRET` | `openssl rand -hex 32` |
| `CORS_ALLOWED_ORIGINS` | `https://observatoriorr.com.br` (separar por vírgula) |
| `R2_PUBLIC_DOMAIN` | `observatoriorr.com.br` (mesmo valor do coletor) |

## Deploy no Railway

1. **solr** — Root Directory `search/solr`, SEM domínio público; volume
   persistente em `/var/solr`; envs `SOLR_HEAP=512m`,
   `SOLR_MODULES=analysis-extras`. Fica acessível só via private
   networking (`solr.railway.internal:8983`).
2. **Postgres** — plugin gerenciado; referenciar `DATABASE_URL` na api.
3. **api** — Root Directory `search/api`, domínio público
   (`busca.observatoriorr.com.br` via CNAME no Cloudflare em modo
   **DNS only/nuvem cinza**, para o cert Let's Encrypt do Railway).

## Decisões de schema (Solr)

- 1 documento por **página** de edição; `id = {chave_pdf}#{pagina}` —
  reindexar é overwrite, idempotente.
- `text_pt_nomes` = StandardTokenizer + ICUFolding, **sem stemming**:
  o caso de uso é nome de pessoa; "José" == "jose" == "JOSÉ" é o que
  importa, stemming pt só geraria falso positivo.
- Schema clássico versionado no git (`schema.xml`); mudou o schema →
  editar arquivo, redeploy do solr e reindexar do R2.
