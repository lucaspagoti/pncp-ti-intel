"""Atas do Compras.gov.br (ARP): colunas de origem, `vigente_na_origem` e fim do log legado.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13

- `atas` ganha o predicado `vigente_na_origem` (SIGA: status `Válida`; ARP: não cancelada e não
  excluída) e os campos que o SIGA não tem (link de origem, órgão, valor, nº de controle PNCP).
- `ata_itens` ganha tipo, códigos de catálogo, quantidade empenhada e limite de adesão.
- As views passam a usar `vigente_na_origem` no lugar do literal `'Válida'`.
- `log_execucao_ingestao` sai: era do ingestor por página, removido na R2 (ADR 0020).

Sem downgrade de dados; faça backup restaurado antes de aplicar.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

HOJE_SP = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_ata_consumo_item")
    op.execute("DROP VIEW IF EXISTS v_ata_itens_ti")
    op.execute("DROP VIEW IF EXISTS v_atas_ti_vigentes")

    op.execute(
        """
        ALTER TABLE atas
            ADD COLUMN vigente_na_origem boolean NOT NULL DEFAULT false,
            ADD COLUMN numero_controle_pncp text,
            ADD COLUMN link_origem text,
            ADD COLUMN orgao text,
            ADD COLUMN valor_total numeric,
            ADD COLUMN quantidade_itens integer,
            ADD COLUMN atualizado_origem text
        """
    )
    op.execute("UPDATE atas SET vigente_na_origem = (status_origem = 'Válida')")
    op.execute("ALTER TABLE atas ALTER COLUMN vigente_na_origem DROP DEFAULT")

    op.execute(
        """
        ALTER TABLE ata_itens
            ADD COLUMN tipo_item text,
            ADD COLUMN codigo_catalogo integer,
            ADD COLUMN codigo_pdm integer,
            ADD COLUMN nome_pdm text,
            ADD COLUMN quantidade_empenhada numeric,
            ADD COLUMN maximo_adesao numeric
        """
    )

    op.execute(
        f"""
        CREATE VIEW v_atas_ti_vigentes AS
        SELECT a.carga_id, a.id_origem AS id_ata, c.fonte, a.numero,
               a.unidade_gerenciadora, a.orgao, a.objeto, a.licitacao, a.inicio, a.fim,
               a.criterio_julgamento, a.status_origem, a.processos, a.motivo_ti,
               a.numero_controle_pncp, a.link_origem, a.valor_total, a.quantidade_itens,
               v.primeira_vez_vista, c.data_referencia
        FROM atas a
        JOIN cargas c ON c.id = a.carga_id AND c.ativa AND c.status = 'concluida'
        LEFT JOIN atas_vistas v ON v.fonte = c.fonte AND v.id_origem = a.id_origem
        WHERE a.is_ti
          AND a.vigente_na_origem
          AND (a.inicio IS NULL OR a.inicio <= {HOJE_SP})
          AND a.fim >= {HOJE_SP}
        """
    )
    op.execute(
        """
        CREATE VIEW v_ata_itens_ti AS
        SELECT v.id_ata, v.fonte, i.id_item, i.descricao, i.nome_catalogo,
               i.tipo_item, i.codigo_catalogo, i.codigo_pdm, i.nome_pdm,
               i.id_fornecedor, i.fornecedor, i.quantidade,
               CASE WHEN i.valor_valido THEN i.valor_unitario END AS valor_unitario,
               i.valor_valido, i.quantidade_empenhada, i.maximo_adesao
        FROM ata_itens i
        JOIN v_atas_ti_vigentes v
          ON v.carga_id = i.carga_id AND v.id_ata = i.ata_id_origem
        """
    )
    op.execute(
        """
        CREATE VIEW v_ata_consumo_item AS
        SELECT v.id_ata, v.fonte, p.id_item, p.item, p.unidade AS unidade_participante,
               p.qtd_demandada, p.qtd_consumida, p.valor_demandado, p.valor_consumido
        FROM ata_participantes p
        JOIN v_atas_ti_vigentes v
          ON v.carga_id = p.carga_id AND v.id_ata = p.ata_id_origem
        """
    )

    views = "v_atas_ti_vigentes, v_ata_itens_ti, v_ata_consumo_item"
    op.execute(f"REVOKE ALL ON {views} FROM ingest, mcp_reader")
    op.execute(f"GRANT SELECT ON {views} TO mcp_reader")

    op.execute("DROP TABLE IF EXISTS log_execucao_ingestao")


def downgrade() -> None:
    raise RuntimeError("0006 não tem downgrade de dados; restaure o backup anterior se necessário")
