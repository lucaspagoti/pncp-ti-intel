"""Troca a base histórica pelo snapshot corrente de atas candidatas a TI.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12

A decisão ADR 0015 elimina os dados históricos locais. Esta migração os remove
apenas quando aplicada explicitamente; não foi executada contra o banco de dev.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Não há snapshot anterior completo: o último estado da F1/F2A é descartado
    # conforme o escopo aceito na ADR 0015. Backup continua sendo responsabilidade
    # explícita do operador antes de aplicar a migração.
    op.execute("DROP VIEW IF EXISTS v_itens_contratacao")
    op.execute("DROP VIEW IF EXISTS v_contratacoes")
    op.execute("DROP VIEW IF EXISTS v_contratos")
    op.execute("DROP VIEW IF EXISTS v_atas")

    op.execute("DROP TABLE IF EXISTS itens_contratacao")
    op.execute("DROP TABLE IF EXISTS contratos")
    op.execute("DROP TABLE IF EXISTS contratacoes")
    op.execute("DROP TABLE IF EXISTS fornecedores")
    op.execute("TRUNCATE TABLE atas, orgaos")

    op.execute(
        """
        CREATE TABLE snapshots_atas_ti (
            id uuid PRIMARY KEY,
            data_referencia date NOT NULL,
            status text NOT NULL CHECK (status IN ('em_andamento', 'concluido', 'falhou')),
            ativo boolean NOT NULL DEFAULT false,
            registros_lidos bigint NOT NULL DEFAULT 0,
            candidatas_ti bigint NOT NULL DEFAULT 0,
            descartadas bigint NOT NULL DEFAULT 0,
            amostra_descartadas integer NOT NULL DEFAULT 0,
            iniciado_em timestamptz NOT NULL DEFAULT now(),
            concluido_em timestamptz,
            erro_tipo text
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_snapshot_atas_ti_ativo ON snapshots_atas_ti (ativo) WHERE ativo"
    )

    op.execute("ALTER TABLE atas DROP CONSTRAINT atas_pkey")
    op.execute("ALTER TABLE atas ADD COLUMN snapshot_id uuid")
    op.execute("ALTER TABLE atas ADD COLUMN chave_snapshot text")
    op.execute(
        "ALTER TABLE atas ADD CONSTRAINT atas_snapshot_id_fkey "
        "FOREIGN KEY (snapshot_id) REFERENCES snapshots_atas_ti(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE atas ALTER COLUMN snapshot_id SET NOT NULL")
    op.execute("ALTER TABLE atas ALTER COLUMN chave_snapshot SET NOT NULL")
    op.execute("ALTER TABLE atas ADD PRIMARY KEY (chave_snapshot)")
    op.execute("CREATE INDEX ix_atas_snapshot_id ON atas (snapshot_id)")
    op.execute("CREATE INDEX ix_atas_numero_controle ON atas (numero_controle_pncp_ata)")

    op.execute(
        """
        CREATE TABLE amostra_atas_descartadas (
            chave_snapshot text PRIMARY KEY,
            snapshot_id uuid NOT NULL REFERENCES snapshots_atas_ti(id) ON DELETE CASCADE,
            numero_controle_pncp_ata text NOT NULL,
            cnpj_orgao varchar(14),
            objeto_contratacao text,
            vigencia_inicio date,
            vigencia_fim date
        )
        """
    )

    op.execute(
        "CREATE VIEW v_atas_ti_vigentes AS "
        "SELECT a.numero_controle_pncp_ata, a.numero_controle_pncp_compra, "
        "a.numero_ata_registro_preco, a.ano_ata, a.cnpj_orgao, a.objeto_contratacao, "
        "a.cancelado, a.data_cancelamento, a.data_assinatura, a.vigencia_inicio, "
        "a.vigencia_fim, a.data_publicacao_pncp, a.data_inclusao, a.data_atualizacao "
        "FROM atas a JOIN snapshots_atas_ti s ON s.id = a.snapshot_id "
        "WHERE s.ativo AND s.status = 'concluido' "
        "AND COALESCE(a.cancelado, false) = false "
        "AND a.vigencia_inicio <= (now() AT TIME ZONE 'America/Sao_Paulo')::date "
        "AND a.vigencia_fim >= (now() AT TIME ZONE 'America/Sao_Paulo')::date"
    )

    op.execute("REVOKE ALL ON atas, snapshots_atas_ti, amostra_atas_descartadas FROM mcp_reader")
    op.execute("REVOKE ALL ON v_atas_ti_vigentes FROM ingest, mcp_reader")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON atas, snapshots_atas_ti, "
        "amostra_atas_descartadas TO ingest"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON orgaos TO ingest")
    op.execute("GRANT SELECT ON v_atas_ti_vigentes TO mcp_reader")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ingest")


def downgrade() -> None:
    # As tabelas e dados históricos removidos na subida não podem ser restaurados
    # pelo downgrade. Recriar a estrutura antiga vazia daria falsa impressão de
    # recuperação; a restauração deve vir de backup explícito.
    raise RuntimeError(
        "0004 é destrutiva e não tem downgrade de dados; restaure o backup anterior se necessário"
    )
