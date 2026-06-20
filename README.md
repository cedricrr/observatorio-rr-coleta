# Observatório Roraima — Coleta

**Observatório Roraima** é um projeto cívico independente que monitora os
diários oficiais do estado de Roraima — arquivando-os de forma imutável,
auditável e pesquisável pelo público. Este repositório reúne todo o pipeline:
coleta, arquivamento, jornal editorial e busca textual.

Fontes monitoradas:

- **TJRR** — Tribunal de Justiça de Roraima
- **MPRR** — Ministério Público de Roraima

O jornal e a busca são publicados em
**[observatoriorr.com.br](https://observatoriorr.com.br)**.

## Acervo

| Fonte    | Cobertura   | Edições |
|----------|-------------|---------|
| **TJRR** | 2003 – 2026 | 4.857   |
| **MPRR** | 2022 – 2026 | 979     |

O MPRR só tem diário próprio desde abr/2022; antes, o conteúdo do Ministério
Público saía como seção dentro do diário do TJRR (já coberto). Todo o acervo
— cerca de 5.800 edições / ~92,5 mil páginas — está indexado para busca
textual integral.

## Como funciona

Três camadas, todas neste repositório:

### 1. Coleta e arquivamento (`scripts/coletar.py`, `fontes/`)

- Descobre novas edições nas fontes oficiais.
- Baixa cada PDF e o envia ao **Cloudflare R2** (arquivo imutável), com hash
  sha256.
- Submete a edição ao Internet Archive (Wayback), em best-effort.
- Grava um JSON de metadados (data, fonte, número, URL original, hash, caminho
  no R2) versionado no git — um histórico auditável. A coleta **não faz
  triagem**: baixa tudo.

### 2. Jornal editorial (`scripts/jornal_diario.py`, `scripts/publicar.py`)

- Converte o PDF em texto, segmenta em matérias e as classifica via **Claude
  API**.
- Renderiza um jornal HTML com os destaques e o publica no R2, junto do índice
  e do sitemap.
- A relevância é decidida aqui, no pipeline editorial — separada da coleta.

### 3. Busca textual (`scripts/cache_texto.py`, `search/`)

- Extrai o texto integral de cada PDF (cache `texto/` no R2) e o indexa no
  **Apache Solr**.
- Uma API **FastAPI** (subprojeto `search/`) serve busca pública por nome,
  termo ou número de processo, com funil freemium e captura de leads. Em
  produção desde junho de 2026.

## Princípios

- **O R2 é o arquivo de registro; o git guarda apenas metadados** imutáveis.
- O índice de busca e o sitemap são **derivados e reconstruíveis** a partir do
  R2 — mesma filosofia do dedupe.
- **Independência editorial**: sem vínculo com órgão público, partido político
  ou veículo de imprensa. A automação coleta tudo; a curadoria incide apenas
  sobre o que vira destaque, nunca sobre o conteúdo dos diários.

## Automação

Roda no **GitHub Actions** em três janelas diárias (Roraima é UTC-4 fixo, sem
horário de verão): arquivamento (~22h), jornal editorial + publicação (~2h) e
uma segunda tentativa condicional (~8h). Cada execução é auto-suficiente — o
dedupe usa o R2 como fonte da verdade.

## Desenvolvimento

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest          # suíte de testes
.venv/bin/ruff check .              # lint
```

Detalhes de arquitetura, comandos e armadilhas estão em
[`CLAUDE.md`](./CLAUDE.md). A busca tem subprojeto próprio em
[`search/`](./search/README.md).

---

Licenciado sob a [MIT License](./LICENSE) ·
mantido por [@cedricrr](https://github.com/cedricrr)
