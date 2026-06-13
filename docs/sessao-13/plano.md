# Plano Sessão 13 · Funil de leads — fase 2

Plano de execução para Claude Code no repositório `observatorio-rr-coleta`.
Metodologia: TDD estrito (RED → revisão dos testes pelo usuário → GREEN), conventional commits, ruff zero warnings em código Python.

Evolui o freemium **já em produção** (Sessão 11): API FastAPI em `search/api` (Railway, projeto `observatorio-busca`), Solr 9 privado, leads em **Postgres** (não D1), token de sessão **itsdangerous** via header `X-Sessao` (não JWT/Bearer). Testes da API com **pytest** (`cd search/api && .venv/bin/python -m pytest`); testes de template com pytest no venv do coletor.

## O que a Sessão 11 já entregou (não refazer)

- Gate servidor de 3 resultados em `POST /buscar`; token `X-Sessao` (180 dias) libera lista completa paginada; `mm=100%`.
- `POST /leads` (e-mail, telefone opcional, 1 checkbox, `origem_busca`) com upsert idempotente por e-mail em Postgres.
- `busca.html.j2` consumindo a API: gate inline, token em `localStorage` (`obs_busca_token`), fallback 401, "Carregar mais".
- CORS por env `CORS_ALLOWED_ORIGINS`; rate limit 30/min busca, 5/min leads.
- Despublicação editorial do incidente ECA art. 143 (4 fases concluídas; 52 matérias em 39 edições).

## Contexto e restrições

1. O domínio `observatoriorr.com.br` é escopo da Sessão 12 (Fase A pronta, fases manuais pendentes). Esta sessão não depende dele; o token em `localStorage` fica vinculado à origem atual e será invalidado no cutover (aceito — leads ficam no Postgres).
2. A degustação de 3 resultados **já é aplicada no servidor** — não mexer. Blur no cliente é apresentação sobre placeholders fictícios, nunca sobre dados reais (o anônimo não recebe os itens bloqueados; só recebe `total_diarios`/`total_ocorrencias`).
3. Sem serviços pagos novos. E-mail transacional segue fora do escopo.
4. Evolução do lead: **nome passa a ser obrigatório**; consentimento vira **granular em 2 checkboxes** (1º obrigatório: relatórios e notificações; 2º opcional, desmarcado: produtos e serviços). Compatibilidade: registros existentes têm `nome NULL` e o consentimento antigo mapeia só para o 1º checkbox.
5. **Bloqueador editorial (vive na Sessão 12)**: a busca indexa o texto integral dos diários, então conteúdo despublicado da camada editorial continua localizável via Solr. A supressão no índice é bloqueador do cutover do domínio e está planejada em `docs/sessao-12/plano.md` — esta sessão só a verifica no checklist final (Ciclo 13.6), sem duplicar o trabalho aqui.

## Ciclo 13.0 · Reconhecimento

1. Documentar em `docs/sessao-13/estado-atual.md` o estado real: contrato atual de `/buscar` e `/leads`, schema da tabela `leads`, pontos de injeção de `SEARCH_API_URL` nos templates, fluxo de build/upload (`scripts/publicar.py`).

Critério de saída: documento aprovado pelo usuário. Nenhuma suposição dos ciclos seguintes sobrevive se contradisser o encontrado.

Commit: `docs(sessao-13): mapeia estado atual da busca e do funil`

## Ciclo 13.1 · Evolução do cadastro de leads (Postgres + classificador)

Objetivo: enriquecer `POST /leads` com nome, consentimento granular, termos da sessão, classe inferida e auditoria.

Schema (evolução do DDL inline em `search/api/app/db.py`, estilo `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — sem ferramenta de migração, mantendo a convenção existente):

```sql
ALTER TABLE leads ADD COLUMN IF NOT EXISTS nome TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS consentimento_relatorios BOOLEAN;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS consentimento_ofertas BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS classe TEXT;           -- 'tecnico' | 'geral' | 'interesse_estado'
ALTER TABLE leads ADD COLUMN IF NOT EXISTS termos_sessao JSONB;   -- termos buscados na sessão
ALTER TABLE leads ADD COLUMN IF NOT EXISTS ip_hash TEXT;          -- SHA-256 truncado, auditoria de consentimento
```

Contrato (evolução do endpoint existente):

```
POST /leads
  body: { nome, email, telefone?, consentimentos: {relatorios, ofertas}, termos: [..] }
  resposta 201: { token }
```

Regras de classificação (módulo puro `search/api/app/classificador.py`, testável isolado):
- Técnico se qualquer termo casar: regex CNJ `\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}`, padrão OAB, vocabulário processual (intimação, acórdão, despacho, sentença, citação, embargos), vocabulário administrativo (portaria, provimento, resolução, designação, remoção), ou sessão com 3+ nomes distintos.
- Geral nos demais casos (nome próprio isolado, vocabulário de concurso, sequência de 11 dígitos).
- Empate resolve para Técnico.

RED (parar para revisão):
- testes do classificador: 1 caso por regra, mais o desempate
- teste: cadastro sem checkbox 1 retorna 422
- teste: checkbox 2 ausente grava FALSE (nunca assume opt-in)
- teste: e-mail duplicado renova consentimento e devolve token sem criar registro novo (upsert existente — cobrir os campos novos no `ON CONFLICT`)
- teste: e-mail inválido retorna 422
- teste: telefone, quando enviado, é normalizado para E.164 BR
- teste: `termos_sessao` é gravado e a classe corresponde aos termos
- teste: `ip_hash` usa o primeiro hop do `X-Forwarded-For` (convenção de `limites.py`), truncado
- teste: resposta nunca inclui dados de outros leads
- teste: payload antigo (sem nome/consentimentos granulares) é rejeitado com mensagem clara — frontend e API sobem juntos

GREEN: implementar Pydantic model novo + classificador + DDL. Rate limit de 5/min permanece.

Commits:
- `test(search): cobre consentimento granular, classificador e termos de sessão`
- `feat(search): leads com nome, consentimento granular e classe tecnico/geral`

## Ciclo 13.2 · Eventos de funil

Objetivo: medir as 4 etapas sem analytics pago (o Cloudflare Web Analytics via `CF_ANALYTICS_TOKEN` mede pageviews; o funil precisa de etapas próprias).

```
POST /eventos  body: { tipo, sessao }
  tipos: 'home_view' | 'busca_exec' | 'gate_view' | 'cadastro_ok'
```

Tabela `eventos` no Postgres (tipo, sessao_id anônimo gerado no cliente, criado_em). Sem IP, sem user agent, sem dado pessoal (evento anterior ao consentimento). Rate limit próprio (slowapi, padrão de `limites.py`).

RED: gravação por tipo; rejeição de tipo desconhecido (422); payload não aceita campos extras (dado pessoal não entra nem por engano).
GREEN: endpoint + `sendBeacon` nos pontos certos do frontend (Ciclo 13.4).

Commit: `feat(search): registra eventos de funil no Postgres`

## Ciclo 13.3 · Templates Jinja2: home e notícia

Objetivo: aplicar os wireframes 7.1 e 7.2 do diagnóstico nos templates reais (`scripts/templates/indice.html.j2` e `jornal.html.j2`; build em `scripts/publicar.py` e `renderizar.py`).

Home (`indice.html.j2`):
1. Zona superior: frase de posicionamento, barra de busca em largura total, seletor de jurisdição (Roraima ativo; Amazonas e Pará com tag "em breve" desabilitada; "Outros estados" abre microformulário que envia `POST /leads` com `classe: 'interesse_estado'` e o estado no campo de termos).
2. O painel de estatísticas do acervo **já existe na home** — evoluir para os contadores do wireframe (total de edições por órgão + data da última edição), mantendo a condicional à env `SEARCH_API_URL`.
3. Módulo de reforço da busca após o editorial.

Notícia (`jornal.html.j2`):
1. Entidades clicáveis: linkar `busca.html?q=<entidade>` apenas para o que já existe estruturado na classificação editorial (contratada, número do procedimento). Sem NER nova.
2. Bloco "Este assunto no acervo" com contagem consultada ao Solr **no build** (cache local; em falha do Solr, omitir o bloco sem quebrar o build — mesma filosofia de resiliência por estágio do pipeline editorial).
3. Bloco de conversão variável por categoria (contratos → "pesquise uma empresa"; concursos → "pesquise seu nome nas convocações"; demais → "monitore publicações com seu nome ou OAB"). Categorias vêm de `CATEGORIAS_VALIDAS` — conferir nomes reais antes de escrever os testes.

RED (pytest, padrão do repo):
- home renderiza barra de busca antes do primeiro item editorial
- contadores refletem o acervo de teste
- seletor contém Roraima ativo e 2 estados "em breve" desabilitados
- notícia de contrato gera link de busca para a contratada
- falha do Solr no build omite o bloco sem erro
- bloco de conversão muda conforme a categoria
- sem `SEARCH_API_URL`, nada disso é emitido (convenção existente)

Commits:
- `test(jornal): cobre nova home e módulos de conversão da notícia`
- `feat(jornal): home com busca em destaque e notícias com ganchos para o acervo`

## Ciclo 13.4 · Busca com blur, página de cadastro e privacidade

Objetivo: aplicar o wireframe 7.3 sobre `busca.html.j2` (que já consome a API).

Busca:
1. **Manter** o fluxo existente (POST `/buscar`, `X-Sessao`, fallback 401, "Carregar mais").
2. Trocar o gate inline por: 3 resultados completos → N placeholders sob blur (divs com texto fictício de tamanho variável gerado no cliente, zero dado real no DOM) → contador "mais N ocorrências encontradas" (derivado de `total_diarios`/`total_ocorrencias` já retornados) → botão "Visualizar mais resultados" → `cadastro.html?q=<termo>&total=<N>`.
3. **Remover o formulário inline atual** (substituído pela página exclusiva).
4. Acumular termos buscados em `sessionStorage` para envio no cadastro.

Cadastro (`cadastro.html.j2`, nova página renderizada e publicada pelo fluxo do `publicar.py`):
1. Wireframe 7.3: termo e contadores da querystring, fundo com placeholders sob blur, card central com nome, e-mail, telefone opcional ("para receber alertas por WhatsApp"), 2 checkboxes com os textos exatos da seção 5.2 do diagnóstico, link para a política de privacidade, botão "Liberar resultados completos", nota "Acesso gratuito. Sem cartão de crédito.".
2. Submit → `POST /leads` (termos do `sessionStorage`) → grava token no `localStorage` (chave `obs_busca_token` existente) → redireciona para `busca.html?q=<termo>` desbloqueada.
3. Validação no cliente espelha a do servidor, nunca a substitui.

Política de privacidade (`privacidade.html.j2`): controlador identificado, finalidades separadas por checkbox, retenção, canal de revogação por e-mail, tratamento de dados publicados em diários oficiais com canal de desindexação (referenciando a prática já adotada no incidente). Link no rodapé de todos os templates.

Testes (pytest sobre o HTML renderizado, padrão do repo; sem vitest):
- 3 resultados reais no DOM e zero dados reais nos placeholders
- botão do gate carrega a querystring correta
- cadastro sem checkbox 1 não submete
- token gravado desbloqueia a busca na volta
- eventos `busca_exec`, `gate_view`, `cadastro_ok` nos pontos certos

Commits:
- `test(jornal): cobre gate visual, cadastro e desbloqueio por token`
- `feat(jornal): degustação com blur, página exclusiva de cadastro e política de privacidade`

## Ciclo 13.5 · Paleta e ajustes visuais

Aplicar a paleta da seção 6.2 como variáveis CSS em **todos** os templates (hoje cada um define o próprio `:root`, com paleta antiga `#c8102e`), sem trocar tipografia (Fraunces, Inter, JetBrains Mono):

```css
:root {
  --cor-primaria: #0F2A3D;
  --cor-primaria-apoio: #1D4E6B;
  --cor-cta: #1E6B4F;
  --cor-fundo: #FAF8F4;
  --cor-superficie: #FFFFFF;
  --cor-texto: #1A1A1A;
  --cor-texto-sec: #5C6670;
  --cor-dado: #B07D2B;
  --cor-em-breve: #8A99A8;
}
```

Blur do gate: `filter: blur(6px) saturate(0.7)`, sem overlay escuro. Verificar contraste AA antes do commit. Atenção: as cores de órgão (`--cor-rule`/`--cor-tjrr`) são usadas como identidade MPRR/TJRR nos resultados — decidir mapeamento na paleta nova.

Commit: `style(jornal): aplica paleta institucional em variáveis CSS`

## Ciclo 13.6 · Deploy e verificação fim a fim

1. Deploy da API pelo fluxo Railway existente (`railway up` de dentro de `search/api` — o diretório linkado é a raiz de build). Sem secrets novos além dos já cadastrados; se algum ciclo exigir um, registrar antes (nunca inventar nomes — conferir contra `config.py`).
2. DDL novo aplica-se sozinho no primeiro request (convenção `IF NOT EXISTS` do `db.py`).
3. Build estático + upload ao R2 via `scripts.publicar` (caminho `workflow_dispatch` do job `publicacao` serve para o deploy do frontend).
4. Checklist manual: resposta anônima não contém itens além de 3 (DevTools/Network); lead grava com nome, classe e consentimentos corretos no Postgres; token desbloqueia; eventos aparecem na tabela; conteúdo suprimido pelo bloqueador da Sessão 12 não retorna na busca (se a supressão já estiver no ar); frontend antigo em cache (max-age=300) não quebra contra a API nova durante a janela de 5 min.

Commit final: `chore(sessao-13): deploy do funil de leads fase 2`

## Fora do escopo

1. Domínio próprio e e-mail transacional (Sessão 12 / futura; alertas por WhatsApp dependem disso).
2. NER nova para entidades não estruturadas.
3. Dashboard de leads/funil (consulta direta ao Postgres via `railway connect` basta no piloto).
4. Dupla confirmação de e-mail (sem provedor; `ip_hash` + `consentimento_em` preservam a prova).
5. OCR de PDFs escaneados (`paginas_vazias`) e refino da regra de iniciais do validador editorial — pendências já registradas, sessões próprias.

## Riscos aceitos

1. Site ainda em `r2.dev` até a Sessão 12 concluir: conversão medida subestima a real; rate limit do bucket público; token preso à origem atual.
2. Janela de incompatibilidade no deploy: o contrato novo de `/leads` rejeita o payload do frontend antigo — deploy da API e publish do frontend devem ser na mesma janela (cache de 5 min na home/busca).
