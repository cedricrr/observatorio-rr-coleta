# Observatório Roraima — Coleta

Parte do **Observatório Roraima**, um projeto cívico independente de
monitoramento de diários oficiais de Roraima. Este repositório é o
coletor responsável por baixar diários oficiais do **MPRR** (Ministério
Público de Roraima) e do **TJRR** (Tribunal de Justiça de Roraima),
armazenar os PDFs no Cloudflare R2 e gerar metadados em JSON
versionados aqui no git.

O jornal editorial gerado a partir da coleta é publicado em
**[observatoriorr.com.br](https://observatoriorr.com.br)**.

## Como funciona

- **Descoberta**: varredura periódica das fontes oficiais para
  identificar novas edições de diários publicadas.
- **Download e armazenamento**: cada PDF é baixado e enviado para um
  bucket no Cloudflare R2, garantindo um arquivo imutável da edição.
- **Metadados versionados**: para cada edição é gerado um JSON com
  metadados (data, fonte, URL original, hash, caminho no R2) e
  commitado neste repositório, criando um histórico auditável.

## Fontes monitoradas

- **MPRR** — Ministério Público de Roraima
- **TJRR** — Tribunal de Justiça de Roraima

## Status

<!-- badges aqui -->

## Política editorial

Este repositório é responsável apenas por **coleta e armazenamento**
dos diários oficiais. Não há triagem editorial aqui: nenhum diário é
lido, filtrado ou priorizado neste pipeline. Toda decisão sobre o que
vira pauta acontece em outro repositório (`observatorio-rr-site`,
ainda em construção).

O Observatório Roraima é um projeto independente, sem vínculo com
qualquer órgão público, partido político ou veículo de imprensa.

---

Licenciado sob a [MIT License](./LICENSE) ·
mantido por [@cedricrr](https://github.com/cedricrr)
