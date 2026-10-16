"""Web local (R4): papel `web_reader` e a view de busca `v_busca_atas`.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16

- Papel `web_reader` (LOGIN, senha de `PNCP_TI_WEB_PASSWORD`): SELECT só nas views da web, sem
  acesso às tabelas base (ADR 0018).
- Extensão `unaccent` (busca sem acento) e `pg_trgm` (ordenação por similaridade).
- `v_busca_atas`: as atas de TI vigentes com o texto de busca (objeto, órgão e itens) e o
  resumo de preço unitário (mín., máx. e a lista de preços válidos, para o filtro de faixa).
  Lê `ata_itens` direto (a view roda com os privilégios do dono).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from pncp_ti.config import exigir, get_settings

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

VIEWS_WEB = "v_atas_ti_vigentes, v_ata_itens_ti, v_ata_consumo_item, v_busca_atas"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        """
        CREATE VIEW v_busca_atas AS
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
    )

    settings = get_settings()
    bind = op.get_bind()
    existe = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'web_reader'")).first()
    if not existe:
        senha = exigir(settings.web_password, "PNCP_TI_WEB_PASSWORD").replace("'", "''")
        bind.exec_driver_sql(
            f"CREATE ROLE web_reader LOGIN PASSWORD '{senha}'",
            execution_options={"no_parameters": True},
        )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM web_reader")
    op.execute(f"GRANT SELECT ON {VIEWS_WEB} TO web_reader")


def downgrade() -> None:
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM web_reader")
    op.execute("DROP VIEW IF EXISTS v_busca_atas")
    # O papel é do cluster (outros bancos podem depender dele): fica, sem privilégios aqui.
