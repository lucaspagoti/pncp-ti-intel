"""Ingestão de contratações — `/v1/contratacoes/publicacao`.

Exige `codigoModalidadeContratacao` por chamada (uma modalidade por vez); a lista
de modalidades vem de `compras_mcp.dominio.MODALIDADES_PNCP` (fonte oficial única,
reusada — não redeclaramos os 13 códigos aqui).
"""

from __future__ import annotations

import psycopg
from compras_mcp.clients.pncp import PNCPClient
from compras_mcp.dominio import MODALIDADES_PNCP

from pncp_ti.ingest.executar import FalhasIngestao, ingerir_janela
from pncp_ti.ingest.mapeadores import extrair_orgao, mapear_contratacao
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import Janela

ENTIDADE = "contratacoes"
PATH = "/v1/contratacoes/publicacao"


async def ingerir(
    conn: psycopg.AsyncConnection,
    cliente: PNCPClient,
    limitador: LimitadorTaxa,
    janela: Janela,
    *,
    forcar: bool = False,
    atualizacoes: bool = False,
) -> None:
    """Consulta publicações e, no diário, alterações de compras antigas."""
    fontes = [(ENTIDADE, PATH)]
    if atualizacoes:
        fontes.append(("contratacoes_atualizacao", "/v1/contratacoes/atualizacao"))
    falhas = 0
    for entidade, path in fontes:
        for modalidade in MODALIDADES_PNCP:
            try:
                await ingerir_janela(
                    conn,
                    cliente,
                    limitador,
                    entidade=entidade,
                    tabela="contratacoes",
                    chave="numero_controle_pncp",
                    path=path,
                    janela=janela,
                    filtros={"codigoModalidadeContratacao": modalidade["codigo"]},
                    mapear=mapear_contratacao,
                    modalidade_id=modalidade["codigo"],
                    extrair_orgao=extrair_orgao,
                    forcar=forcar,
                )
            except FalhasIngestao as exc:
                falhas += exc.falhas
    if falhas:
        raise FalhasIngestao(falhas)
