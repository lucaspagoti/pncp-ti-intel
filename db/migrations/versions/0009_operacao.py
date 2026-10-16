"""R6: outbox persistente e unidades de preço derivadas (ADR 0022).

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE notificacoes (
            chave text PRIMARY KEY,
            corpo text NOT NULL,
            criado_em timestamptz NOT NULL DEFAULT now(),
            enviado_em timestamptz,
            tentativas integer NOT NULL DEFAULT 0,
            erro_tipo text
        )
    """)
    op.execute("""
        CREATE TABLE digest_atas (
            identidade text PRIMARY KEY,
            notificacao text NOT NULL REFERENCES notificacoes(chave)
        )
    """)
    op.execute(
        "CREATE INDEX ix_notificacoes_pendentes ON notificacoes(criado_em) WHERE enviado_em IS NULL"
    )
    op.execute("REVOKE ALL ON notificacoes, digest_atas FROM PUBLIC, mcp_reader")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON notificacoes, digest_atas TO ingest")
    op.execute("GRANT SELECT ON v_atas_ti_vigentes TO ingest")
    # Conservador: reconhece a unidade explicitamente declarada no texto do item.
    # Não infere duração nem divide preço anual por 12 sem base na origem.
    op.execute(r"""
        CREATE FUNCTION unidade_preco_ti(descricao text) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
            WITH texto AS (
                SELECT translate(lower(descricao),
                    'áàâãäéèêëíìîïóòôõöúùûüç',
                    'aaaaaeeeeiiiiooooouuuuc') AS t
            ), sinais AS (
                SELECT
                    t ~ '^[[:space:]]*licencas?[[:space:]]*(/|por[[:space:]]+)'
                        '[[:space:]]*mes[[:space:]]*$'
                        OR t ~ '^[[:space:]]*licencas?[[:space:]]+(mensal|mensais)'
                               '[[:space:]]*$' AS licenca,
                    t ~ '^[[:space:]]*usuarios?[[:space:]]*(/|por[[:space:]]+)'
                        '[[:space:]]*ano[[:space:]]*$'
                        OR t ~ '^[[:space:]]*usuarios?[[:space:]]+anual[[:space:]]*$' AS usuario,
                    t ~ '^[[:space:]]*paginas?[[:space:]]+impressas?'
                        '([[:space:]]+a[345])?[[:space:]]*$' AS pagina
                FROM texto
            )
            SELECT CASE WHEN licenca::int + usuario::int + pagina::int <> 1 THEN NULL
                        WHEN licenca THEN 'licença/mês'
                        WHEN usuario THEN 'usuário/ano'
                        WHEN pagina THEN 'página impressa' END
            FROM sinais
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION unidade_preco_ti(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION unidade_preco_ti(text) TO ingest, mcp_reader")
    op.execute("""
        CREATE VIEW v_ata_precos_ti AS
        SELECT i.*, unidade_preco_ti(i.descricao) AS unidade_preco,
               CASE WHEN unidade_preco_ti(i.descricao) IS NOT NULL
                    THEN i.valor_unitario END AS preco_por_unidade
        FROM v_ata_itens_ti i
    """)
    op.execute("GRANT SELECT ON v_ata_precos_ti TO mcp_reader")
    # R4 pode criar web_reader antes ou depois desta revisão; o runbook cobre o grant tardio.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_reader') THEN
                GRANT SELECT ON v_ata_precos_ti TO web_reader;
                GRANT EXECUTE ON FUNCTION unidade_preco_ti(text) TO web_reader;
            END IF;
        END $$
    """)


def downgrade() -> None:
    op.execute("REVOKE SELECT ON v_atas_ti_vigentes FROM ingest")
    op.execute("DROP VIEW v_ata_precos_ti")
    op.execute("DROP FUNCTION unidade_preco_ti(text)")
    op.execute("DROP TABLE digest_atas, notificacoes")
