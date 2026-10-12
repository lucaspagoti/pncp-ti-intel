"""Ingestão de contratos — `/v1/contratos`. Sem modalidade obrigatória."""

from __future__ import annotations

import psycopg
from compras_mcp.clients.pncp import PNCPClient

from pncp_ti.ingest.executar import ingerir_janela
from pncp_ti.ingest.mapeadores import extrair_fornecedor, extrair_orgao, mapear_contrato
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import Janela

ENTIDADE = "contratos"
PATH = "/v1/contratos"


async def ingerir(
    conn: psycopg.AsyncConnection,
    cliente: PNCPClient,
    limitador: LimitadorTaxa,
    janela: Janela,
    *,
    forcar: bool = False,
) -> None:
    await ingerir_janela(
        conn,
        cliente,
        limitador,
        entidade=ENTIDADE,
        tabela="contratos",
        chave="numero_controle_pncp",
        path=PATH,
        janela=janela,
        filtros={},
        mapear=mapear_contrato,
        extrair_orgao=extrair_orgao,
        extrair_fornecedor=extrair_fornecedor,
        forcar=forcar,
    )
