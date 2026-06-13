"""Persistência de leads no Postgres (psycopg3, sem ORM).

PII fica SÓ aqui: nunca no R2 público, nunca no git. O DDL roda na
mesma conexão do insert (CREATE TABLE IF NOT EXISTS + ALTER TABLE ...
ADD COLUMN IF NOT EXISTS) — uma tabela só não justifica ferramenta de
migração, e o volume é baixo o bastante para conexão por request.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Json

DDL_TABELA = """
CREATE TABLE IF NOT EXISTS leads (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email TEXT NOT NULL,
  telefone TEXT,
  consentimento_em TIMESTAMPTZ NOT NULL,
  finalidade TEXT NOT NULL,
  origem_busca TEXT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

DDL_INDICE = """
CREATE UNIQUE INDEX IF NOT EXISTS leads_email_unico ON leads (lower(email))
"""

# Sessão 13: colunas novas do funil. origem_busca permanece só para as
# linhas históricas (substituída por termos_sessao). O UPDATE final mapeia
# o consentimento antigo (1 checkbox) para o 1º checkbox novo.
DDL_EVOLUCAO_SESSAO_13 = (
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS nome TEXT",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS consentimento_relatorios BOOLEAN",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS consentimento_ofertas BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS classe TEXT",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS termos_sessao JSONB",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS ip_hash TEXT",
    "UPDATE leads SET consentimento_relatorios = TRUE WHERE consentimento_relatorios IS NULL",
)

# Re-cadastro renova o consentimento e atualiza o perfil; telefone só
# sobrescreve se veio preenchido.
SQL_UPSERT = """
INSERT INTO leads (nome, email, telefone, consentimento_em,
                   consentimento_relatorios, consentimento_ofertas,
                   classe, termos_sessao, ip_hash, finalidade)
VALUES (%(nome)s, %(email)s, %(telefone)s, now(),
        %(consentimento_relatorios)s, %(consentimento_ofertas)s,
        %(classe)s, %(termos_sessao)s, %(ip_hash)s, %(finalidade)s)
ON CONFLICT (lower(email)) DO UPDATE SET
  nome = EXCLUDED.nome,
  telefone = COALESCE(EXCLUDED.telefone, leads.telefone),
  consentimento_em = now(),
  consentimento_relatorios = EXCLUDED.consentimento_relatorios,
  consentimento_ofertas = EXCLUDED.consentimento_ofertas,
  classe = EXCLUDED.classe,
  termos_sessao = EXCLUDED.termos_sessao,
  ip_hash = EXCLUDED.ip_hash,
  finalidade = EXCLUDED.finalidade
"""


def gravar_lead(
    database_url: str,
    *,
    nome: str,
    email: str,
    telefone: str | None,
    consentimento_relatorios: bool,
    consentimento_ofertas: bool,
    classe: str,
    termos_sessao: list[str],
    ip_hash: str,
    finalidade: str,
) -> None:
    """Grava (ou renova) um lead. Upsert por e-mail case-insensitive."""
    with psycopg.connect(database_url) as conn:
        conn.execute(DDL_TABELA)
        conn.execute(DDL_INDICE)
        for ddl in DDL_EVOLUCAO_SESSAO_13:
            conn.execute(ddl)
        conn.execute(
            SQL_UPSERT,
            {
                "nome": nome,
                "email": email,
                "telefone": telefone,
                "consentimento_relatorios": consentimento_relatorios,
                "consentimento_ofertas": consentimento_ofertas,
                "classe": classe,
                "termos_sessao": Json(termos_sessao),
                "ip_hash": ip_hash,
                "finalidade": finalidade,
            },
        )


def ping_db(database_url: str) -> bool:
    """True se o Postgres responde."""
    try:
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False
