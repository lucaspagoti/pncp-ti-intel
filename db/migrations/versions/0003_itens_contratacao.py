"""Fase 2A — itens de contratação (CATMAT/CATSER, unidade, preço unitário).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12

"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE itens_contratacao (
            chave text PRIMARY KEY,
            numero_controle_pncp text NOT NULL,
            numero_item integer NOT NULL,
            descricao_resumida text,
            descricao_detalhada text,
            material_ou_servico varchar(1),
            codigo_item_catalogo integer,
            codigo_grupo integer,
            codigo_classe integer,
            unidade_medida text,
            quantidade numeric,
            valor_unitario_estimado numeric,
            valor_total_estimado numeric,
            valor_unitario_resultado numeric,
            valor_total_resultado numeric,
            fornecedor_id text REFERENCES fornecedores(fornecedor_id),
            ni_fornecedor varchar(14),
            nome_fornecedor text,
            situacao_compra_item text,
            tem_resultado boolean,
            data_inclusao_pncp timestamptz,
            raw jsonb NOT NULL,
            ingerido_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Sem FK para `contratacoes`: mesma decisão já tomada para
    # `contratos.numero_controle_pncp_compra`/`atas.numero_controle_pncp_compra`
    # (migração 0001) — o item pode ser ingerido antes ou fora da janela em que
    # a compra-pai foi ingerida, e isso não pode derrubar o item inteiro.
    op.execute("CREATE INDEX ix_itens_numero_controle ON itens_contratacao (numero_controle_pncp)")
    op.execute("CREATE INDEX ix_itens_codigo_catalogo ON itens_contratacao (codigo_item_catalogo)")
    op.execute("CREATE INDEX ix_itens_fornecedor_id ON itens_contratacao (fornecedor_id)")

    op.execute(
        "CREATE VIEW v_itens_contratacao AS SELECT "
        "chave, numero_controle_pncp, numero_item, descricao_resumida, descricao_detalhada, "
        "material_ou_servico, codigo_item_catalogo, codigo_grupo, codigo_classe, unidade_medida, "
        "quantidade, valor_unitario_estimado, valor_total_estimado, valor_unitario_resultado, "
        "valor_total_resultado, ni_fornecedor, nome_fornecedor, situacao_compra_item, "
        "tem_resultado, data_inclusao_pncp "
        "FROM itens_contratacao"
    )

    op.execute("GRANT SELECT, INSERT, UPDATE ON itens_contratacao TO ingest")
    op.execute("GRANT SELECT ON v_itens_contratacao TO mcp_reader")


def downgrade() -> None:
    op.execute("REVOKE ALL ON itens_contratacao, v_itens_contratacao FROM ingest, mcp_reader")
    op.execute("DROP VIEW IF EXISTS v_itens_contratacao")
    op.execute("DROP TABLE IF EXISTS itens_contratacao")
