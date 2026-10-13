"""Modelo multi-fonte de atas: cargas, atas, itens, participantes e views (ADR 0019).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13

Substitui as tabelas do snapshot `/v1/atas` (ADR 0015, substituída pela ADR 0016). Elas
estavam vazias: nenhuma versão do snapshot nacional foi publicada. A migração é destrutiva
para esse schema e não tem downgrade; faça backup restaurado antes de aplicar.
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

HOJE_SP = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"


def upgrade() -> None:
    # Guarda: o schema antigo só pode sair se nunca publicou um snapshot completo.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM snapshots_atas_ti WHERE ativo AND status = 'concluido') THEN
                RAISE EXCEPTION
                    '0005 recusada: há snapshot /v1/atas concluido e ativo; faça backup e '
                    'remova-o conscientemente antes de aplicar (migração destrutiva)';
            END IF;
        END $$
        """
    )
    op.execute("DROP VIEW IF EXISTS v_atas_ti_vigentes")
    op.execute("DROP TABLE IF EXISTS amostra_atas_descartadas")
    op.execute("DROP TABLE IF EXISTS atas")
    op.execute("DROP TABLE IF EXISTS snapshots_atas_ti")
    op.execute("DROP TABLE IF EXISTS orgaos")

    op.execute(
        """
        CREATE TABLE cargas (
            id uuid PRIMARY KEY,
            fonte text NOT NULL,
            data_referencia date NOT NULL,
            status text NOT NULL CHECK (
                status IN ('em_andamento', 'concluida', 'substituida', 'sem_mudanca', 'falhou')
            ),
            ativa boolean NOT NULL DEFAULT false,
            iniciado_em timestamptz NOT NULL DEFAULT now(),
            concluido_em timestamptz,
            geracao jsonb NOT NULL DEFAULT '{}'::jsonb,
            contagens jsonb NOT NULL DEFAULT '{}'::jsonb,
            erro_tipo text,
            erro_mensagem text,
            CONSTRAINT ck_cargas_ativa_concluida CHECK (NOT ativa OR status = 'concluida')
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_cargas_ativa ON cargas (fonte) WHERE ativa")
    op.execute("CREATE INDEX ix_cargas_fonte_iniciado ON cargas (fonte, iniciado_em DESC)")

    op.execute(
        """
        CREATE TABLE atas (
            carga_id uuid NOT NULL REFERENCES cargas(id) ON DELETE CASCADE,
            id_origem text NOT NULL,
            numero text NOT NULL,
            unidade_gerenciadora text,
            objeto text NOT NULL,
            licitacao text,
            inicio date,
            fim date,
            criterio_julgamento text,
            status_origem text NOT NULL,
            processos text[] NOT NULL DEFAULT '{}',
            is_ti boolean NOT NULL,
            motivo_ti text,
            PRIMARY KEY (carga_id, id_origem)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE ata_itens (
            carga_id uuid NOT NULL,
            chave text NOT NULL,
            ata_id_origem text NOT NULL,
            id_item text NOT NULL,
            descricao text NOT NULL,
            nome_catalogo text NOT NULL,
            id_fornecedor text,
            fornecedor text,
            quantidade numeric,
            valor_unitario numeric,
            taxa_pct numeric,
            valor_valido boolean NOT NULL,
            PRIMARY KEY (carga_id, chave),
            FOREIGN KEY (carga_id, ata_id_origem)
                REFERENCES atas (carga_id, id_origem) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_ata_itens_ata ON ata_itens (carga_id, ata_id_origem)")

    op.execute(
        """
        CREATE TABLE ata_participantes (
            carga_id uuid NOT NULL,
            chave text NOT NULL,
            ata_id_origem text NOT NULL,
            id_item text NOT NULL,
            item text NOT NULL,
            unidade text NOT NULL,
            qtd_demandada numeric,
            qtd_consumida numeric,
            valor_demandado numeric,
            valor_consumido numeric,
            PRIMARY KEY (carga_id, chave),
            FOREIGN KEY (carga_id, ata_id_origem)
                REFERENCES atas (carga_id, id_origem) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_ata_part_ata ON ata_participantes (carga_id, ata_id_origem)")

    # Fora do snapshot: a troca de carga não "renova" atas já conhecidas (digest, R6).
    op.execute(
        """
        CREATE TABLE atas_vistas (
            fonte text NOT NULL,
            id_origem text NOT NULL,
            primeira_vez_vista date NOT NULL,
            PRIMARY KEY (fonte, id_origem)
        )
        """
    )

    # Vigente = status de origem `Válida` E datas cobrindo hoje (America/Sao_Paulo).
    # Início vazio é aceito (2 atas válidas no CSV de 13/10/2026); fim vazio, não.
    op.execute(
        f"""
        CREATE VIEW v_atas_ti_vigentes AS
        SELECT a.carga_id, a.id_origem AS id_ata, c.fonte, a.numero,
               a.unidade_gerenciadora, a.objeto, a.licitacao, a.inicio, a.fim,
               a.criterio_julgamento, a.status_origem, a.processos, a.motivo_ti,
               v.primeira_vez_vista, c.data_referencia
        FROM atas a
        JOIN cargas c ON c.id = a.carga_id AND c.ativa AND c.status = 'concluida'
        LEFT JOIN atas_vistas v ON v.fonte = c.fonte AND v.id_origem = a.id_origem
        WHERE a.is_ti
          AND a.status_origem = 'Válida'
          AND (a.inicio IS NULL OR a.inicio <= {HOJE_SP})
          AND a.fim >= {HOJE_SP}
        """
    )
    op.execute(
        """
        CREATE VIEW v_ata_itens_ti AS
        SELECT v.id_ata, v.fonte, i.id_item, i.descricao, i.nome_catalogo,
               i.id_fornecedor, i.fornecedor, i.quantidade,
               CASE WHEN i.valor_valido THEN i.valor_unitario END AS valor_unitario,
               i.valor_valido
        FROM ata_itens i
        JOIN v_atas_ti_vigentes v
          ON v.carga_id = i.carga_id AND v.id_ata = i.ata_id_origem
        """
    )
    # Demandado x consumido por unidade participante. Não é saldo disponível:
    # há linhas com consumo maior que a demanda no CSV de origem.
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

    tabelas = "cargas, atas, ata_itens, ata_participantes, atas_vistas"
    views = "v_atas_ti_vigentes, v_ata_itens_ti, v_ata_consumo_item"
    op.execute(f"REVOKE ALL ON {tabelas} FROM mcp_reader")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tabelas} TO ingest")
    op.execute(f"REVOKE ALL ON {views} FROM ingest, mcp_reader")
    op.execute(f"GRANT SELECT ON {views} TO mcp_reader")


def downgrade() -> None:
    raise RuntimeError(
        "0005 é destrutiva e não tem downgrade de dados; restaure o backup anterior se necessário"
    )
