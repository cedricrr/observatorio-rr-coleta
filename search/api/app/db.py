"""Persistência de leads no Postgres (psycopg3, sem ORM).

PII fica SÓ aqui: nunca no R2 público, nunca no git. O DDL roda na
mesma conexão do insert (CREATE TABLE IF NOT EXISTS) — uma tabela só
não justifica ferramenta de migração, e o volume é baixo o bastante
para conexão por request.
"""

from __future__ import annotations

import psycopg

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

# Re-cadastro renova o consentimento e completa dados que faltavam
# (telefone só sobrescreve se veio preenchido).
SQL_UPSERT = """
INSERT INTO leads (email, telefone, consentimento_em, finalidade, origem_busca)
VALUES (%(email)s, %(telefone)s, now(), %(finalidade)s, %(origem_busca)s)
ON CONFLICT (lower(email)) DO UPDATE SET
  telefone = COALESCE(EXCLUDED.telefone, leads.telefone),
  consentimento_em = now(),
  finalidade = EXCLUDED.finalidade,
  origem_busca = EXCLUDED.origem_busca
"""


def gravar_lead(
    database_url: str,
    *,
    email: str,
    telefone: str | None,
    finalidade: str,
    origem_busca: str | None,
) -> None:
    """Grava (ou renova) um lead. Upsert por e-mail case-insensitive."""
    with psycopg.connect(database_url) as conn:
        conn.execute(DDL_TABELA)
        conn.execute(DDL_INDICE)
        conn.execute(
            SQL_UPSERT,
            {
                "email": email,
                "telefone": telefone,
                "finalidade": finalidade,
                "origem_busca": origem_busca,
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
