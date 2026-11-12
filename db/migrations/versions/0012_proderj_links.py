"""W10: link da contratação no site do PRODERJ (ADR 0042).

- `proderj_links`: uma linha por processo SEI encontrado nas listas de licitações do site do
  PRODERJ (`rj.gov.br/proderj/licitacoes`), presa a uma carga (`cargas.fonte = 'proderj'`) que
  troca de forma atômica como as demais. Só guarda o endereço da página e o título; vigência,
  órgão e itens continuam vindo do SIGA.
- `proderj_processo(texto)`: normaliza o número do processo (`SEI-430002/000030/2024`,
  `SEI - 430002/30/2024`, `430002/001112//2024`) para `430002/30/2024`. A mesma regra existe
  em `pncp_ti.fontes.proderj.normalizar_processo`; os testes comparam as duas.
- `v_ata_proderj`: atas do SIGA do PRODERJ que a web mostra, com a URL da contratação quando
  achada na carga ativa (`url` nula quando não consta no site). É a única coisa nova que o
  `web_reader` lê.
- `v_cargas_web` deixa de listar `proderj`: link não é dado de ata, e o rodapé "Dados de" não
  deve recuar por causa dele.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ORGAO_SEI = "430002"  # código do PRODERJ no SEI-RJ
# Classes explícitas, iguais às de `fontes/proderj.py`: `\\s` e `\\d` do Postgres dependem da
# collation e divergiriam do Python (QA-W10-01).
ESPACO = "[ \\t\\r\\n\\u00a0\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]"
E = ESPACO
PROCESSO_RE = f"({ORGAO_SEI}){E}*/{E}*0*([0-9]+){E}*/+{E}*([0-9]{{4}})"


def upgrade() -> None:
    op.execute(f"""
        CREATE FUNCTION proderj_processo(texto text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
            SELECT m[1] || '/' || ltrim(m[2], '0') || '/' || m[3]
            FROM (SELECT regexp_match(texto, '{PROCESSO_RE}') AS m) x
            WHERE m IS NOT NULL AND ltrim(m[2], '0') <> ''
        $$
    """)
    op.execute("""
        CREATE TABLE proderj_links (
            carga_id uuid NOT NULL REFERENCES cargas (id) ON DELETE CASCADE,
            processo text NOT NULL,
            node_id integer NOT NULL,
            url text NOT NULL,
            titulo text NOT NULL,
            lista text NOT NULL,
            PRIMARY KEY (carga_id, processo),
            CONSTRAINT ck_proderj_url CHECK (url LIKE 'https://www.rj.gov.br/proderj/%')
        )
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON proderj_links TO ingest")
    op.execute("""
        CREATE VIEW v_ata_proderj AS
        SELECT b.fonte, b.id_ata, l.url
        FROM v_busca_atas b
        LEFT JOIN LATERAL (
            SELECT pl.url
            FROM proderj_links pl
            JOIN cargas c ON c.id = pl.carga_id AND c.ativa AND c.fonte = 'proderj'
            WHERE pl.processo IN (SELECT proderj_processo(p) FROM unnest(b.processos) AS p)
            ORDER BY pl.processo
            LIMIT 1
        ) l ON true
        WHERE b.fonte = 'siga_rj' AND b.unidade_gerenciadora ILIKE 'PRODERJ%'
    """)
    op.execute("GRANT SELECT ON v_ata_proderj TO web_reader")
    op.execute("""
        CREATE OR REPLACE VIEW v_cargas_web AS
        SELECT fonte, data_referencia, concluido_em
        FROM cargas WHERE ativa AND status = 'concluida' AND fonte <> 'proderj'
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW v_cargas_web AS
        SELECT fonte, data_referencia, concluido_em
        FROM cargas WHERE ativa AND status = 'concluida'
    """)
    op.execute("DROP VIEW v_ata_proderj")
    op.execute("DROP TABLE proderj_links")
    op.execute("DROP FUNCTION proderj_processo(text)")
