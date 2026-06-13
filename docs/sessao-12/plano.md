# Plano Sessão 12 · Lançamento do domínio observatoriorr.com.br

Estado: **Fase A (código) concluída** no commit `2479065` — canonical/OG/favicon, página Sobre,
robots.txt + sitemap.xml na raiz, beacon condicional do Web Analytics, `scripts/migrar_dominio.py`
e `R2Client.listar`. Pendem as fases manuais (DNS/Cloudflare, migração dos artefatos publicados,
cutover) e o bloqueador editorial abaixo.

---

## BLOQUEADOR · Supressão de conteúdo sensível no índice de busca (Solr)

**Nenhum cutover público do domínio antes desta supressão estar no ar.**

### Contexto (sem conteúdo sensível neste documento)

O incidente de proteção a menores (ECA art. 143, `docs/incidentes/2026-06-10-protecao-menores.md`)
foi tratado em 4 fases na **camada editorial**: 52 matérias despublicadas em 39 edições,
validador determinístico (`scripts/validador_sensivel.py`) no funil de publicação, regra no
classificador. A pendência registrada na Fase 4 é exatamente esta: a **camada de busca**
(`texto/` no R2 + Solr) indexa o **texto integral** dos PDFs de todas as ~2.226 edições e ficou
fora do escopo das 4 fases. Resultado: o conteúdo despublicado do jornal continua localizável
por nome via `POST /buscar` — e a busca existe justamente para localizar nomes.

Por que é bloqueador da Sessão 12: o cutover para o domínio próprio amplia alcance, confiança e
indexação por buscadores externos. Aumentar a audiência da busca antes da supressão amplia a
exposição que a despublicação editorial reduziu.

Detalhes identificáveis (manchetes, números SIMP, termos casados) permanecem **fora do git**,
na cópia de auditoria local gitignored (`data/incidentes/`).

### Opções avaliadas

**A — Filtro sensível por página no funil do `/indexar` (recomendada).**
Módulo de regras na API (`search/api`), aplicado quando o documento de texto chega ao
`/indexar`: página que casa não entra no índice (resposta passa a reportar `indexadas` +
`suprimidas`). Mesma filosofia do validador da Fase 3 no `processar_chave`: funil único, então
**sobrevive a reindexações por construção** (o índice é derivado e reconstruível de `texto/`).
Cobre as ~2.226 edições indexadas e todas as futuras — não só as 39 com camada editorial.
Para o acervo já indexado: purga via medição read-only sobre `texto/` (ver "Execução") seguida
de delete por id (`{chave_pdf}#{pagina}`), ou reindex completo através do funil novo.

**B — Supressão pontual das edições do incidente.**
Delete-by-query das páginas das edições afetadas. Simples, mas não sistêmico: novas edições
sensíveis continuam entrando; reindexação ressuscita o conteúdo a menos que exista lista de
exclusão consultada no `/indexar` (que já é metade da opção A); e remove páginas inteiras com
conteúdo legítimo sem critério.

**C — Filtro em query-time.**
Índice intacto; exclusão por `fq` com lista de ids suprimidos na consulta. Reversível e barato,
mas o conteúdo permanece no índice (qualquer rota de consulta nova que esqueça o filtro vaza) e
a lista pontual tem o mesmo problema de cobertura da opção B.

### Recomendação

Opção **A**, em dois passos com gate de revisão entre eles (padrão `--preparar`/`--executar`
do `despublicar_lote.py`):

1. **Medição (somente leitura, nada sobe)**: script que varre `texto/` no R2 aplicando o
   conjunto de regras proposto e reporta taxa de páginas suprimidas por órgão/ano + amostra
   dos matches (gravada em `data/incidentes/`, gitignored). As regras partem do subconjunto de
   **alta precisão** do validador da Fase 3 (crime sexual + menor, idade exata + menor,
   destituição/adoção + iniciais) — texto integral de diário oficial cita termos jurídicos com
   frequência muito maior que manchetes editoriais, então a regra de iniciais e os padrões
   amplos fail-closed da Fase 3 teriam taxa de falso positivo alta demais aqui. Calibrar com
   os números na mão.
2. **Aplicação**: filtro no `/indexar` (TDD, deploy Railway) + purga do já indexado com os ids
   da medição. Verificação: termos do incidente não retornam; páginas legítimas das mesmas
   edições continuam buscáveis.

Trade-off aceito: páginas suprimidas ficam fora da busca, mas o PDF oficial e o `texto/`
permanecem no arquivo (política do projeto: a fonte primária é arquivada integralmente; a
supressão cobre a camada de **acesso por busca**, que é o que amplifica a exposição).

### Registro da decisão

- Decisão: _pendente — aguardando escolha da política e revisão da medição._
- Executado em: _pendente._

---

## Fases manuais restantes (B/C/D)

Documentadas fora deste arquivo quando forem executadas (DNS/Cloudflare Transform Rule,
`migrar_dominio.py` nos artefatos publicados + commit manual único, troca de
`R2_PUBLIC_DOMAIN` no `.env`/secrets, validação pós-cutover). Lembrete já registrado: o
cutover invalida os tokens de desbloqueio da busca presos à origem `r2.dev` (aceito — leads
ficam no Postgres) e o domínio `busca.*` para a API entra nesse mesmo movimento.
