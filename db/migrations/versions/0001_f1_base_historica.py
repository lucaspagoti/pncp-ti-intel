"""Fase 1 — base histórica: schema, papéis e views.

Revision ID: 0001
Revises:
Create Date: 2026-10-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from pncp_ti.config import get_settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE orgaos (
            cnpj varchar(14) PRIMARY KEY,
            razao_social text,
            poder_id varchar(1),
            esfera_id varchar(1),
            atualizado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE fornecedores (
            ni varchar(14) PRIMARY KEY,
            tipo_pessoa varchar(2),
            razao_social_nome text,
            atualizado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE contratacoes (
            numero_controle_pncp text PRIMARY KEY,
            cnpj_orgao varchar(14) REFERENCES orgaos(cnpj),
            uf_sigla varchar(2),
            municipio_nome text,
            codigo_ibge_municipio integer,
            codigo_unidade text,
            nome_unidade text,
            ano_compra integer,
            sequencial_compra integer,
            numero_compra text,
            processo text,
            objeto_compra text,
            modalidade_id integer,
            modalidade_nome text,
            situacao_compra_id integer,
            situacao_compra_nome text,
            srp boolean,
            valor_total_estimado numeric,
            valor_total_homologado numeric,
            data_publicacao_pncp timestamptz,
            data_inclusao timestamptz,
            data_atualizacao timestamptz,
            data_atualizacao_global timestamptz,
            data_abertura_proposta timestamptz,
            data_encerramento_proposta timestamptz,
            link_sistema_origem text,
            link_processo_eletronico text,
            raw jsonb NOT NULL,
            ingerido_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_contratacoes_modalidade ON contratacoes (modalidade_id)")
    op.execute(
        "CREATE INDEX ix_contratacoes_data_publicacao ON contratacoes (data_publicacao_pncp)"
    )
    op.execute("CREATE INDEX ix_contratacoes_cnpj_orgao ON contratacoes (cnpj_orgao)")

    op.execute(
        """
        CREATE TABLE atas (
            numero_controle_pncp_ata text PRIMARY KEY,
            numero_controle_pncp_compra text,
            numero_ata_registro_preco text,
            ano_ata integer,
            cnpj_orgao varchar(14) REFERENCES orgaos(cnpj),
            objeto_contratacao text,
            cancelado boolean,
            data_cancelamento timestamptz,
            data_assinatura date,
            vigencia_inicio date,
            vigencia_fim date,
            data_publicacao_pncp timestamptz,
            data_inclusao timestamptz,
            data_atualizacao timestamptz,
            data_atualizacao_global timestamptz,
            raw jsonb NOT NULL,
            ingerido_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_atas_compra ON atas (numero_controle_pncp_compra)")
    op.execute("CREATE INDEX ix_atas_vigencia_fim ON atas (vigencia_fim)")
    op.execute("CREATE INDEX ix_atas_cnpj_orgao ON atas (cnpj_orgao)")

    op.execute(
        """
        CREATE TABLE contratos (
            numero_controle_pncp text PRIMARY KEY,
            numero_controle_pncp_compra text,
            numero_controle_pncp_ata text,
            cnpj_orgao varchar(14) REFERENCES orgaos(cnpj),
            ni_fornecedor varchar(14) REFERENCES fornecedores(ni),
            ano_contrato integer,
            sequencial_contrato integer,
            numero_contrato_empenho text,
            processo text,
            objeto_contrato text,
            valor_inicial numeric,
            valor_parcela numeric,
            valor_global numeric,
            valor_acumulado numeric,
            numero_parcelas integer,
            data_assinatura date,
            data_vigencia_inicio date,
            data_vigencia_fim date,
            data_publicacao_pncp timestamptz,
            data_atualizacao timestamptz,
            data_atualizacao_global timestamptz,
            raw jsonb NOT NULL,
            ingerido_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_contratos_compra ON contratos (numero_controle_pncp_compra)")
    op.execute("CREATE INDEX ix_contratos_cnpj_orgao ON contratos (cnpj_orgao)")
    op.execute("CREATE INDEX ix_contratos_ni_fornecedor ON contratos (ni_fornecedor)")

    op.execute(
        """
        CREATE TABLE log_execucao_ingestao (
            id bigserial PRIMARY KEY,
            entidade text NOT NULL,
            modalidade_id integer,
            janela_inicio date NOT NULL,
            janela_fim date NOT NULL,
            pagina integer NOT NULL,
            registros_lidos integer NOT NULL DEFAULT 0,
            registros_gravados integer NOT NULL DEFAULT 0,
            falhas integer NOT NULL DEFAULT 0,
            status text NOT NULL,
            erro_mensagem text,
            iniciado_em timestamptz NOT NULL DEFAULT now(),
            concluido_em timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_log_execucao_combo
        ON log_execucao_ingestao (
            entidade, coalesce(modalidade_id, -1), janela_inicio, janela_fim, pagina
        )
        WHERE status = 'ok'
        """
    )

    op.execute(
        "CREATE VIEW v_contratacoes AS SELECT "
        "numero_controle_pncp, cnpj_orgao, uf_sigla, municipio_nome, codigo_ibge_municipio, "
        "codigo_unidade, nome_unidade, ano_compra, sequencial_compra, numero_compra, processo, "
        "objeto_compra, modalidade_id, modalidade_nome, situacao_compra_id, situacao_compra_nome, "
        "srp, valor_total_estimado, valor_total_homologado, data_publicacao_pncp, data_inclusao, "
        "data_atualizacao, data_atualizacao_global, data_abertura_proposta, "
        "data_encerramento_proposta, link_sistema_origem, link_processo_eletronico "
        "FROM contratacoes"
    )
    op.execute(
        "CREATE VIEW v_atas AS SELECT "
        "numero_controle_pncp_ata, numero_controle_pncp_compra, numero_ata_registro_preco, "
        "ano_ata, cnpj_orgao, objeto_contratacao, cancelado, data_cancelamento, data_assinatura, "
        "vigencia_inicio, vigencia_fim, data_publicacao_pncp, data_inclusao, data_atualizacao, "
        "data_atualizacao_global "
        "FROM atas"
    )
    op.execute(
        "CREATE VIEW v_contratos AS SELECT "
        "numero_controle_pncp, numero_controle_pncp_compra, numero_controle_pncp_ata, "
        "cnpj_orgao, ni_fornecedor, ano_contrato, sequencial_contrato, numero_contrato_empenho, "
        "processo, objeto_contrato, valor_inicial, valor_parcela, valor_global, valor_acumulado, "
        "numero_parcelas, data_assinatura, data_vigencia_inicio, data_vigencia_fim, "
        "data_publicacao_pncp, data_atualizacao, data_atualizacao_global "
        "FROM contratos"
    )

    settings = get_settings()
    bind = op.get_bind()
    existing_roles = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('ingest', 'mcp_reader')")
        )
    }
    # CREATE ROLE é DDL puro — o parser do Postgres não aceita placeholder ($1) na
    # posição do PASSWORD, só literal. Senha vem só do `.env` local (nunca de
    # entrada externa), mas escapamos a aspa simples mesmo assim por hábito seguro.
    if "ingest" not in existing_roles:
        senha = settings.ingest_password.replace("'", "''")
        bind.exec_driver_sql(f"CREATE ROLE ingest LOGIN PASSWORD '{senha}'")
    if "mcp_reader" not in existing_roles:
        senha = settings.reader_password.replace("'", "''")
        bind.exec_driver_sql(f"CREATE ROLE mcp_reader LOGIN PASSWORD '{senha}'")

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON "
        "orgaos, fornecedores, contratacoes, atas, contratos, log_execucao_ingestao "
        "TO ingest"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ingest")
    op.execute("GRANT SELECT ON v_contratacoes, v_atas, v_contratos TO mcp_reader")


def downgrade() -> None:
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ingest, mcp_reader")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ingest")
    op.execute("DROP VIEW IF EXISTS v_contratos")
    op.execute("DROP VIEW IF EXISTS v_atas")
    op.execute("DROP VIEW IF EXISTS v_contratacoes")
    op.execute("DROP TABLE IF EXISTS log_execucao_ingestao")
    op.execute("DROP TABLE IF EXISTS contratos")
    op.execute("DROP TABLE IF EXISTS atas")
    op.execute("DROP TABLE IF EXISTS contratacoes")
    op.execute("DROP TABLE IF EXISTS fornecedores")
    op.execute("DROP TABLE IF EXISTS orgaos")
    op.execute("DROP ROLE IF EXISTS ingest")
    op.execute("DROP ROLE IF EXISTS mcp_reader")
