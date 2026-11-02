"""W3: busca focada no item principal (ADR 0036).

- `mv_busca_itens`: um item de TI vigente por linha, com a *cabeça* do item (o nome do catálogo,
  ou o texto da descrição antes da primeira vírgula, ponto e vírgula, dois-pontos ou " - "), em
  vetor `simple` (palavra exata) e `portuguese` (radical). É o que diz qual é o item principal da
  ata. O texto inteiro do item vai em `texto_exato` (`simple`), para o preço seguir o item que
  cita o termo.
- `mv_busca_atas`: o `documento` ganha pesos (objeto A, cabeças dos itens B, texto completo C) e a
  coluna `objeto_exato` (`simple`). A recuperação não muda: o texto completo continua no documento.
- `mv_busca_vocabulario`: palavras das cabeças, para o "você quis dizer" (`pg_trgm`).
- `atualizar_busca()` atualiza as três, nesta ordem.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

HOJE_SP = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"


def _cabeca_texto(descricao: str, catalogo: str) -> str:
    """Nome do item como na fonte: o catálogo, ou a descrição até o primeiro separador."""
    return (
        f"left(btrim(COALESCE(NULLIF(btrim({catalogo}), ''), "
        f"split_part(regexp_replace({descricao}, '\\s+-\\s+|[;:]', ',', 'g'), ',', 1))), 120)"
    )


def _cabeca(descricao: str, catalogo: str) -> str:
    return f"unaccent(lower({_cabeca_texto(descricao, catalogo)}))"


CABECA_TEXTO = _cabeca_texto("i.descricao", "i.nome_catalogo")
CABECA = _cabeca("i.descricao", "i.nome_catalogo")
CABECA_IT = _cabeca("it.descricao", "it.nome_catalogo")


def _busca(cabecas: bool) -> str:
    """Base de `mv_busca_atas` (a da 0010, com ou sem a agregação das cabeças dos itens)."""
    coluna = f", string_agg({CABECA_IT}, ' ') AS cabecas" if cabecas else ""
    return f"""
    SELECT v.*,
           COALESCE(i.n_itens, 0) AS n_itens,
           i.preco_min,
           i.preco_max,
           COALESCE(i.precos, '{{}}') AS precos,
           unaccent(lower(concat_ws(' ', v.objeto, v.orgao, v.unidade_gerenciadora, v.numero,
                                    i.textos))) AS texto_busca{", i.cabecas" if cabecas else ""}
    FROM v_atas_ti_vigentes v
    LEFT JOIN LATERAL (
        SELECT count(*)::int AS n_itens,
               min(it.valor_unitario) FILTER (WHERE it.valor_valido) AS preco_min,
               max(it.valor_unitario) FILTER (WHERE it.valor_valido) AS preco_max,
               array_agg(it.valor_unitario) FILTER (WHERE it.valor_valido) AS precos,
               string_agg(concat_ws(' ', it.descricao, it.nome_catalogo), ' ') AS textos{coluna}
        FROM ata_itens it
        WHERE it.carga_id = v.carga_id AND it.ata_id_origem = v.id_ata
    ) i ON true
"""


VIEW_BUSCA = f"""
    CREATE VIEW v_busca_atas AS
    SELECT * FROM mv_busca_atas
    WHERE fim >= {HOJE_SP} AND (inicio IS NULL OR inicio <= {HOJE_SP})
"""


def _indices_atas() -> None:
    op.execute("CREATE UNIQUE INDEX ux_mv_busca_atas ON mv_busca_atas (fonte, id_ata)")
    op.execute("CREATE INDEX ix_mv_busca_atas_documento ON mv_busca_atas USING gin (documento)")
    op.execute("CREATE INDEX ix_mv_busca_atas_fim ON mv_busca_atas (fim)")


def upgrade() -> None:
    op.execute("DROP VIEW v_busca_atas")
    op.execute("DROP MATERIALIZED VIEW mv_busca_atas")
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW mv_busca_atas AS
        SELECT b.*,
               setweight(to_tsvector('portuguese', unaccent(lower(COALESCE(b.objeto, '')))), 'A')
               || setweight(to_tsvector('portuguese', COALESCE(b.cabecas, '')), 'B')
               || setweight(to_tsvector('portuguese', b.texto_busca), 'C') AS documento,
               to_tsvector('simple', unaccent(lower(COALESCE(b.objeto, '')))) AS objeto_exato
        FROM ({_busca(cabecas=True)}) b
        """
    )
    _indices_atas()
    op.execute(VIEW_BUSCA)

    op.execute(
        f"""
        CREATE MATERIALIZED VIEW mv_busca_itens AS
        SELECT v.fonte, v.id_ata, i.carga_id, i.chave, i.id_item,
               {CABECA} AS cabeca,
               {CABECA_TEXTO} AS cabeca_texto,
               CASE WHEN i.valor_valido THEN i.valor_unitario END AS valor_unitario,
               i.quantidade,
               to_tsvector('simple', {CABECA}) AS cabeca_exata,
               to_tsvector('portuguese', {CABECA}) AS cabeca_pt,
               to_tsvector('simple', unaccent(lower(concat_ws(' ', i.descricao, i.nome_catalogo))))
                   AS texto_exato
        FROM ata_itens i
        JOIN v_atas_ti_vigentes v ON v.carga_id = i.carga_id AND v.id_ata = i.ata_id_origem
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_mv_busca_itens ON mv_busca_itens (carga_id, chave)")
    op.execute("CREATE INDEX ix_mv_busca_itens_ata ON mv_busca_itens (fonte, id_ata)")
    op.execute("CREATE INDEX ix_mv_busca_itens_exata ON mv_busca_itens USING gin (cabeca_exata)")
    op.execute("CREATE INDEX ix_mv_busca_itens_pt ON mv_busca_itens USING gin (cabeca_pt)")
    op.execute("CREATE INDEX ix_mv_busca_itens_texto ON mv_busca_itens USING gin (texto_exato)")
    op.execute("""
        CREATE VIEW v_busca_itens AS
        SELECT fonte, id_ata, id_item, cabeca, cabeca_texto, valor_unitario, quantidade,
               cabeca_exata, cabeca_pt, texto_exato
        FROM mv_busca_itens
    """)

    op.execute(r"""
        CREATE MATERIALIZED VIEW mv_busca_vocabulario AS
        SELECT palavra, count(*)::int AS n
        FROM mv_busca_itens, regexp_split_to_table(cabeca, '[^a-z0-9]+') AS palavra
        WHERE length(palavra) >= 4
        GROUP BY palavra
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_busca_vocabulario ON mv_busca_vocabulario (palavra)")
    op.execute(
        "CREATE INDEX ix_mv_busca_vocabulario_trgm ON mv_busca_vocabulario "
        "USING gin (palavra gin_trgm_ops)"
    )
    op.execute("CREATE VIEW v_busca_vocabulario AS SELECT palavra, n FROM mv_busca_vocabulario")

    # Itens antes das atas e o vocabulário por último (ele lê mv_busca_itens).
    op.execute("""
        CREATE OR REPLACE FUNCTION atualizar_busca() RETURNS void
        LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
            REFRESH MATERIALIZED VIEW CONCURRENTLY mv_busca_itens;
            REFRESH MATERIALIZED VIEW CONCURRENTLY mv_busca_atas;
            REFRESH MATERIALIZED VIEW CONCURRENTLY mv_busca_vocabulario;
        $$
    """)
    op.execute(
        "REVOKE ALL ON mv_busca_atas, mv_busca_itens, mv_busca_vocabulario FROM PUBLIC, mcp_reader"
    )
    op.execute("GRANT SELECT ON v_busca_atas, v_busca_itens, v_busca_vocabulario TO web_reader")


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION atualizar_busca() RETURNS void
        LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
        AS 'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_busca_atas'
    """)
    op.execute("DROP VIEW v_busca_vocabulario")
    op.execute("DROP MATERIALIZED VIEW mv_busca_vocabulario")
    op.execute("DROP VIEW v_busca_itens")
    op.execute("DROP MATERIALIZED VIEW mv_busca_itens")
    op.execute("DROP VIEW v_busca_atas")
    op.execute("DROP MATERIALIZED VIEW mv_busca_atas")
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW mv_busca_atas AS
        SELECT b.*, to_tsvector('portuguese', b.texto_busca) AS documento
        FROM ({_busca(cabecas=False)}) b
        """
    )
    _indices_atas()
    op.execute(VIEW_BUSCA)
    op.execute("REVOKE ALL ON mv_busca_atas FROM PUBLIC, mcp_reader")
    op.execute("GRANT SELECT ON v_busca_atas TO web_reader")
