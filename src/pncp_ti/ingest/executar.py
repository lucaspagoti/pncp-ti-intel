"""Núcleo compartilhado da ingestão: pagina uma janela, faz upsert item a item e
grava o log de execução (ADR 0005) — usado pelos três adaptadores de entidade
(contratações, atas, contratos).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import psycopg
import structlog
from compras_mcp.clients.pncp import PNCPClient
from compras_mcp.errors import (
    ComprasHTTPError,
    ComprasRateLimitError,
    ComprasServerError,
    ComprasTimeoutError,
)

from pncp_ti.db import upsert
from pncp_ti.ingest.log import ja_concluida, registrar
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import Janela

log = structlog.get_logger(__name__)

TAMANHO_PAGINA = 50
MAX_TENTATIVAS_PAGINA = 6
BACKOFF_INICIAL_SEGUNDOS = 15.0
BACKOFF_MAXIMO_SEGUNDOS = 180.0

Mapeador = Callable[[dict[str, Any]], dict[str, Any]]
Extrator = Callable[[dict[str, Any]], dict[str, Any] | None]


async def _buscar_pagina(
    cliente: PNCPClient, path: str, *, pagina: int, janela: Janela, filtros: dict[str, Any]
) -> dict[str, Any]:
    """Busca uma página, absorvendo dois comportamentos reais do PNCP:

    - 204 com corpo vazio quando a combinação não tem nenhum resultado (o
      `BaseAsyncClient` reusado levanta `ComprasHTTPError` ao tentar decodificar
      JSON vazio) — tratamos como página vazia de verdade, não como falha.
    - 429 sustentado além dos 2 retries já embutidos no cliente (backfill
      nacional de meses bate nisso em modalidades concorridas, confirmado nesta
      sessão) — fazemos backoff próprio e tentamos de novo, em vez de deixar o
      job inteiro de horas morrer por uma janela de rate limit passageira.
    """
    espera = BACKOFF_INICIAL_SEGUNDOS
    for tentativa in range(1, MAX_TENTATIVAS_PAGINA + 1):
        try:
            return await cliente.list_resource(
                path,
                pagina=pagina,
                tamanho_pagina=TAMANHO_PAGINA,
                dataInicial=janela.inicio.strftime("%Y%m%d"),
                dataFinal=janela.fim.strftime("%Y%m%d"),
                **filtros,
            )
        except ComprasHTTPError as exc:
            if "Resposta nao-JSON" in str(exc):
                return {"data": [], "totalPaginas": 0}
            if (
                isinstance(exc, (ComprasRateLimitError, ComprasServerError, ComprasTimeoutError))
                and tentativa < MAX_TENTATIVAS_PAGINA
            ):
                log.warning(
                    "ingest.retry_apos_erro_transiente",
                    path=path,
                    pagina=pagina,
                    tentativa=tentativa,
                    espera=espera,
                    erro=str(exc),
                )
                await asyncio.sleep(espera)
                espera = min(espera * 2, BACKOFF_MAXIMO_SEGUNDOS)
                continue
            raise
    raise AssertionError("inalcançável: o loop sempre retorna ou levanta antes de esgotar")


async def ingerir_janela(
    conn: psycopg.AsyncConnection,
    cliente: PNCPClient,
    limitador: LimitadorTaxa,
    *,
    entidade: str,
    tabela: str,
    chave: str,
    path: str,
    janela: Janela,
    filtros: dict[str, Any],
    mapear: Mapeador,
    modalidade_id: int | None = None,
    extrair_orgao: Extrator | None = None,
    extrair_fornecedor: Extrator | None = None,
    forcar: bool = False,
) -> None:
    """Pagina `path` na janela dada até esgotar, com upsert e log por página.

    Resumível: uma página já registrada como `ok` no log é pulada. Se a janela
    inteira já foi processada antes, isso custa só uma chamada extra (a primeira
    página além do fim real, que a API responde vazia) antes de parar — barato
    o bastante pra não precisar guardar o total de páginas por fora do log.
    """
    pagina = 1
    while True:
        if not forcar and await ja_concluida(conn, entidade, modalidade_id, janela, pagina):
            pagina += 1
            continue

        await limitador.aguardar()
        try:
            resp = await _buscar_pagina(
                cliente, path, pagina=pagina, janela=janela, filtros=filtros
            )
        except Exception as exc:
            await registrar(
                conn,
                entidade=entidade,
                modalidade_id=modalidade_id,
                janela=janela,
                pagina=pagina,
                registros_lidos=0,
                registros_gravados=0,
                falhas=1,
                status="erro",
                erro_mensagem=str(exc)[:500],
            )
            await conn.commit()
            raise

        itens = resp.get("data") or []
        gravados = 0
        falhas = 0
        for item in itens:
            try:
                if extrair_orgao is not None:
                    orgao = extrair_orgao(item)
                    if orgao is not None:
                        await upsert(conn, "orgaos", "cnpj", orgao)
                if extrair_fornecedor is not None:
                    fornecedor = extrair_fornecedor(item)
                    if fornecedor is not None:
                        await upsert(conn, "fornecedores", "ni", fornecedor)
                await upsert(conn, tabela, chave, mapear(item))
                gravados += 1
            except Exception:
                falhas += 1
                log.exception("ingest.item_falhou", entidade=entidade, pagina=pagina)

        total_paginas = resp.get("totalPaginas") or 0
        await registrar(
            conn,
            entidade=entidade,
            modalidade_id=modalidade_id,
            janela=janela,
            pagina=pagina,
            registros_lidos=len(itens),
            registros_gravados=gravados,
            falhas=falhas,
            status="ok",
        )
        await conn.commit()

        log.info(
            "ingest.pagina_concluida",
            entidade=entidade,
            janela_inicio=str(janela.inicio),
            janela_fim=str(janela.fim),
            pagina=pagina,
            total_paginas=total_paginas,
            registros=len(itens),
        )
        if not itens or pagina >= total_paginas:
            break
        pagina += 1
