"""W1: busca materializada, cargas para a web e cache de unidades gerenciadoras (ADR 0034, 0035).

Revision ID: 0010
Revises: 0009

- `mv_busca_atas`: o conteúdo de `v_busca_atas` (0008) materializado, com o `tsvector` pronto
  (`documento`) e índice GIN. A view calculava `to_tsvector` e agregava os itens a cada busca
  (3,7 s em "notebook" com 20 mil atas, 02/11/2026).
- `v_busca_atas` passa a ler a MV e reaplica o filtro de vigência com a data de hoje: a MV é
  atualizada só depois de cada carga, e a ata que vence à meia-noite não pode esperar a próxima.
- `atualizar_busca()`: `REFRESH ... CONCURRENTLY` (não bloqueia leituras), `SECURITY DEFINER`
  para o papel `ingest` chamar no fim de cada carga sem ser dono da MV.
- `v_cargas_web`: fonte, data de referência e conclusão da carga ativa (rodapé "Dados de").
- `unidades_gerenciadoras`: cache do cadastro de unidades do PNCP, que dá esfera, UF e
  município às atas do ARP (a API `modulo-arp` não traz esses campos).

Quem recriar `v_atas_ti_vigentes` precisa derrubar e recriar `mv_busca_atas` (dependência).
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

HOJE_SP = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"

BUSCA_0008 = """
    SELECT v.*,
           COALESCE(i.n_itens, 0) AS n_itens,
           i.preco_min,
           i.preco_max,
           COALESCE(i.precos, '{}') AS precos,
           unaccent(lower(concat_ws(' ', v.objeto, v.orgao, v.unidade_gerenciadora, v.numero,
                                    i.textos))) AS texto_busca
    FROM v_atas_ti_vigentes v
    LEFT JOIN LATERAL (
        SELECT count(*)::int AS n_itens,
               min(it.valor_unitario) FILTER (WHERE it.valor_valido) AS preco_min,
               max(it.valor_unitario) FILTER (WHERE it.valor_valido) AS preco_max,
               array_agg(it.valor_unitario) FILTER (WHERE it.valor_valido) AS precos,
               string_agg(concat_ws(' ', it.descricao, it.nome_catalogo), ' ') AS textos
        FROM ata_itens it
        WHERE it.carga_id = v.carga_id AND it.ata_id_origem = v.id_ata
    ) i ON true
"""


def upgrade() -> None:
    op.execute("DROP VIEW v_busca_atas")
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW mv_busca_atas AS
        SELECT b.*, to_tsvector('portuguese', b.texto_busca) AS documento
        FROM ({BUSCA_0008}) b
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_mv_busca_atas ON mv_busca_atas (fonte, id_ata)")
    op.execute("CREATE INDEX ix_mv_busca_atas_documento ON mv_busca_atas USING gin (documento)")
    op.execute("CREATE INDEX ix_mv_busca_atas_fim ON mv_busca_atas (fim)")
    op.execute(
        f"""
        CREATE VIEW v_busca_atas AS
        SELECT * FROM mv_busca_atas
        WHERE fim >= {HOJE_SP} AND (inicio IS NULL OR inicio <= {HOJE_SP})
        """
    )
    op.execute("""
        CREATE FUNCTION atualizar_busca() RETURNS void
        LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
        AS 'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_busca_atas'
    """)
    op.execute("REVOKE ALL ON FUNCTION atualizar_busca() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION atualizar_busca() TO ingest")

    op.execute("""
        CREATE VIEW v_cargas_web AS
        SELECT fonte, data_referencia, concluido_em
        FROM cargas WHERE ativa AND status = 'concluida'
    """)

    op.execute("""
        CREATE TABLE unidades_gerenciadoras (
            cnpj text NOT NULL,
            codigo text NOT NULL,
            esfera text,
            uf text,
            municipio text,
            consultado_em timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (cnpj, codigo)
        )
    """)

    op.execute("REVOKE ALL ON mv_busca_atas, unidades_gerenciadoras FROM PUBLIC, mcp_reader")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON unidades_gerenciadoras TO ingest")
    op.execute("GRANT SELECT ON v_busca_atas, v_cargas_web TO web_reader")


def downgrade() -> None:
    op.execute("DROP TABLE unidades_gerenciadoras")
    op.execute("DROP VIEW v_cargas_web")
    op.execute("DROP FUNCTION atualizar_busca()")
    op.execute("DROP VIEW v_busca_atas")
    op.execute("DROP MATERIALIZED VIEW mv_busca_atas")
    op.execute(f"CREATE VIEW v_busca_atas AS {BUSCA_0008}")
    op.execute("GRANT SELECT ON v_busca_atas TO web_reader")
