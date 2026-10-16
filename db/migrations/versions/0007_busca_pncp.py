"""Busca PNCP (R3): esfera/UF/município nas atas e dedupe com o ARP na view.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-16

- `atas` ganha `esfera`, `uf` e `municipio` (a busca PNCP os traz; o SIGA é sempre Estadual/RJ,
  derivado na view; o ARP fica nulo até haver fonte confiável).
- `v_atas_ti_vigentes` esconde a ata da busca PNCP quando o ARP ativo já tem a mesma
  `numero_controle_pncp` como ata de TI vigente (o ARP tem preferência: traz itens, ADR 0016).
- Índice em `numero_controle_pncp` para o dedupe.

As views são recriadas sem perda de dados; as tabelas só ganham colunas nulas.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

HOJE_SP = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"
VIEWS = "v_atas_ti_vigentes, v_ata_itens_ti, v_ata_consumo_item"


def _criar_views(com_dedupe: bool) -> None:
    extras = (
        ", COALESCE(a.esfera, CASE c.fonte WHEN 'siga_rj' THEN 'Estadual' END) AS esfera"
        ", COALESCE(a.uf, CASE c.fonte WHEN 'siga_rj' THEN 'RJ' END) AS uf"
        ", a.municipio"
        if com_dedupe
        else ""
    )
    dedupe = (
        """
          AND NOT (
              c.fonte = 'pncp_busca' AND a.numero_controle_pncp IS NOT NULL AND EXISTS (
                  SELECT 1
                  FROM atas arp
                  JOIN cargas carp ON carp.id = arp.carga_id
                       AND carp.ativa AND carp.status = 'concluida'
                       AND carp.fonte = 'compras_arp'
                  WHERE arp.numero_controle_pncp = a.numero_controle_pncp
                    AND arp.is_ti AND arp.vigente_na_origem
                    AND (arp.inicio IS NULL OR arp.inicio <= {HOJE_SP})
                    AND arp.fim >= {HOJE_SP}
              )
          )"""
        if com_dedupe
        else ""
    ).replace("{HOJE_SP}", HOJE_SP)
    op.execute(
        f"""
        CREATE VIEW v_atas_ti_vigentes AS
        SELECT a.carga_id, a.id_origem AS id_ata, c.fonte, a.numero,
               a.unidade_gerenciadora, a.orgao, a.objeto, a.licitacao, a.inicio, a.fim,
               a.criterio_julgamento, a.status_origem, a.processos, a.motivo_ti,
               a.numero_controle_pncp, a.link_origem, a.valor_total, a.quantidade_itens,
               v.primeira_vez_vista, c.data_referencia{extras}
        FROM atas a
        JOIN cargas c ON c.id = a.carga_id AND c.ativa AND c.status = 'concluida'
        LEFT JOIN atas_vistas v ON v.fonte = c.fonte AND v.id_origem = a.id_origem
        WHERE a.is_ti
          AND a.vigente_na_origem
          AND (a.inicio IS NULL OR a.inicio <= {HOJE_SP})
          AND a.fim >= {HOJE_SP}{dedupe}
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
    op.execute(f"REVOKE ALL ON {VIEWS} FROM ingest, mcp_reader")
    op.execute(f"GRANT SELECT ON {VIEWS} TO mcp_reader")


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_ata_consumo_item")
    op.execute("DROP VIEW IF EXISTS v_ata_itens_ti")
    op.execute("DROP VIEW IF EXISTS v_atas_ti_vigentes")
    op.execute(
        "ALTER TABLE atas ADD COLUMN esfera text, ADD COLUMN uf text, ADD COLUMN municipio text"
    )
    op.execute("CREATE INDEX ix_atas_controle_pncp ON atas (numero_controle_pncp)")
    _criar_views(com_dedupe=True)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_ata_consumo_item")
    op.execute("DROP VIEW IF EXISTS v_ata_itens_ti")
    op.execute("DROP VIEW IF EXISTS v_atas_ti_vigentes")
    op.execute("DROP INDEX IF EXISTS ix_atas_controle_pncp")
    op.execute("ALTER TABLE atas DROP COLUMN esfera, DROP COLUMN uf, DROP COLUMN municipio")
    _criar_views(com_dedupe=False)
