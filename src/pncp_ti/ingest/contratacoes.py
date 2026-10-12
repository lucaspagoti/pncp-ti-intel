"""Ingestão de contratações — `/v1/contratacoes/publicacao`.

Exige `codigoModalidadeContratacao` por chamada (uma modalidade por vez); a lista
de modalidades vem de `compras_mcp.dominio.MODALIDADES_PNCP` (fonte oficial única,
reusada — não redeclaramos os 13 códigos aqui).
"""

from __future__ import annotations

import psycopg
from compras_mcp.clients.pncp import PNCPClient
from compras_mcp.dominio import MODALIDADES_PNCP

from pncp_ti.ingest.executar import ingerir_janela
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
) -> None:
    for modalidade in MODALIDADES_PNCP:
        await ingerir_janela(
            conn,
            cliente,
            limitador,
            entidade=ENTIDADE,
            tabela="contratacoes",
            chave="numero_controle_pncp",
            path=PATH,
            janela=janela,
            filtros={"codigoModalidadeContratacao": modalidade["codigo"]},
            mapear=mapear_contratacao,
            modalidade_id=modalidade["codigo"],
            extrair_orgao=extrair_orgao,
            forcar=forcar,
        )
