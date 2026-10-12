"""Ingestão de atas — `/v1/atas`.

Sem modalidade obrigatória, mas o filtro `dataInicial`/`dataFinal` é por
*sobreposição de vigência*, não por data de publicação (confirmado por chamada
real: uma janela de hoje já traz quase 500 mil atas nacionalmente, porque toda
ata ainda vigente aparece). Isso é esperado e inofensivo aqui — o upsert por
chave natural absorve a mesma ata aparecendo em várias janelas do backfill.
"""

from __future__ import annotations

import psycopg
from compras_mcp.clients.pncp import PNCPClient

from pncp_ti.ingest.executar import ingerir_janela
from pncp_ti.ingest.mapeadores import extrair_orgao_de_ata, mapear_ata
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import Janela

ENTIDADE = "atas"
PATH = "/v1/atas"


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
        tabela="atas",
        chave="numero_controle_pncp_ata",
        path=PATH,
        janela=janela,
        filtros={},
        mapear=mapear_ata,
        extrair_orgao=extrair_orgao_de_ata,
        forcar=forcar,
    )
