"""Núcleo compartilhado: pagina a janela, faz upsert por registro e grava o log
de execução (ADR 0005). O snapshot de atas usa o filtro de inclusão antes do upsert.
"""

from __future__ import annotations

import asyncio
import re
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
from pncp_ti.ingest.log import registrar
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import Janela

log = structlog.get_logger(__name__)

TAMANHO_PAGINA = 50
MAX_TENTATIVAS_PAGINA = 6
BACKOFF_INICIAL_SEGUNDOS = 15.0
BACKOFF_MAXIMO_SEGUNDOS = 180.0

Mapeador = Callable[[dict[str, Any]], dict[str, Any]]
Extrator = Callable[[dict[str, Any]], dict[str, Any] | None]
Incluir = Callable[[dict[str, Any]], bool]


class FalhasIngestao(RuntimeError):
    """Falhas de registros após persistir os válidos e concluir a paginação."""

    def __init__(self, falhas: int) -> None:
        self.falhas = falhas
        super().__init__(f"ingestão incompleta: {falhas} falha(s)")


def _filtros_data_pncp(janela: Janela) -> dict[str, str]:
    return {
        "dataInicial": janela.inicio.strftime("%Y%m%d"),
        "dataFinal": janela.fim.strftime("%Y%m%d"),
    }


def _validar_pagina(
    resp: Any, pagina: int = 1, *, chave_dados: str = "data"
) -> tuple[list[dict[str, Any]], int]:
    """Rejeita envelopes malformados sem interpretá-los como resultado vazio.

    `chave_dados` permite validar envelopes com nomes de lista distintos.
    """
    if not isinstance(resp, dict):
        raise ValueError("envelope inválido")
    itens = resp.get(chave_dados)
    total = resp.get("totalPaginas")
    if not isinstance(itens, list) or any(not isinstance(item, dict) for item in itens):
        raise ValueError("data deve ser lista de objetos")
    if type(total) is not int or total < 0 or (itens and total == 0):
        raise ValueError("totalPaginas inválido")
    if not itens and (pagina != 1 or total != 0):
        raise ValueError("página vazia durante paginação incompleta")
    if itens and pagina > total:
        raise ValueError("página ultrapassa o total declarado")
    if "numeroPagina" in resp and (
        type(resp["numeroPagina"]) is not int or resp["numeroPagina"] != pagina
    ):
        raise ValueError("numeroPagina não corresponde à página pedida")
    return itens, total


def _e_corpo_vazio(exc: ComprasHTTPError) -> bool:
    """True só quando a mensagem indica corpo de verdade vazio (o 204 real).

    A mensagem do `BaseAsyncClient` reusado é sempre
    `"Resposta nao-JSON de {api}{path}: {resp.text[:200]}"` — isolamos o que
    vem depois do único ": " (api/path do PNCP nunca têm dois-pontos) e só
    tratamos como página vazia se esse resto for realmente vazio. Um 200 com
    JSON truncado/corrompido tem texto ali e cai como erro de verdade, não
    fica mascarado de "sem resultado" (e preso pra sempre pelo índice único
    parcial `WHERE status = 'ok'`).
    """
    mensagem = str(exc)
    if "Resposta nao-JSON" not in mensagem:
        return False
    _, _, corpo = mensagem.partition(": ")
    return corpo.strip() == ""


def _e_http_transitorio(exc: ComprasHTTPError) -> bool:
    """Detecta respostas HTTP pontuais que podem desaparecer no retry.

    O cliente compartilhado classifica 429/5xx/timeout, mas outros status
    (por exemplo, uma resposta transitória do gateway) chegam como
    `ComprasHTTPError` genérico. Não repetir erro de JSON ou 404 permanente.
    """
    correspondencia = re.search(r"respondeu (\d{3}):", str(exc))
    if not correspondencia:
        return False
    status = int(correspondencia.group(1))
    return status in {400, 403, 408, 425} or 500 <= status < 600


async def _buscar_pagina(
    cliente: PNCPClient,
    path: str,
    *,
    pagina: int,
    janela: Janela,
    filtros: dict[str, Any],
    formatar_filtros_data: Callable[[Janela], dict[str, str]] = _filtros_data_pncp,
    chave_dados: str = "data",
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
                **formatar_filtros_data(janela),
                **filtros,
            )
        except ComprasHTTPError as exc:
            if _e_corpo_vazio(exc):
                # A chave do envelope precisa casar com `_validar_pagina`.
                return {chave_dados: [], "totalPaginas": 0}
            retentavel = isinstance(
                exc, (ComprasRateLimitError, ComprasServerError, ComprasTimeoutError)
            ) or _e_http_transitorio(exc)
            if retentavel and tentativa < MAX_TENTATIVAS_PAGINA:
                log.warning(
                    "ingest.retry_apos_erro_transiente",
                    path=path,
                    pagina=pagina,
                    tentativa=tentativa,
                    espera=espera,
                    erro_tipo=type(exc).__name__,
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
    chave_dados: str = "data",
    formatar_filtros_data: Callable[[Janela], dict[str, str]] = _filtros_data_pncp,
    forcar: bool = False,
    incluir: Incluir | None = None,
) -> None:
    """Reprocessa a janela inteira: páginas do PNCP são mutáveis.

    Savepoints preservam itens válidos. Falhas são agregadas e sinalizadas ao
    final, sem registrar payloads, mensagens externas ou variáveis locais.
    `forcar` permanece aceito por compatibilidade; toda execução atualiza dados.
    """
    pagina = 1
    total_falhas = 0
    total_paginas_esperadas = 0
    while True:
        await limitador.aguardar()
        try:
            resp = await _buscar_pagina(
                cliente,
                path,
                pagina=pagina,
                janela=janela,
                filtros=filtros,
                formatar_filtros_data=formatar_filtros_data,
                chave_dados=chave_dados,
            )
            itens, total_paginas = _validar_pagina(resp, pagina, chave_dados=chave_dados)
            # Uma redução no total anunciado não autoriza publicar uma carga
            # que ainda não percorreu todas as páginas já prometidas pela fonte.
            total_paginas_esperadas = max(total_paginas_esperadas, total_paginas)
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
                erro_mensagem=type(exc).__name__,
            )
            await conn.commit()
            raise

        gravados = 0
        falhas = 0
        for item in itens:
            try:
                if incluir is not None and not incluir(item):
                    continue
                # Savepoint por item: se o upsert de um item falhar (CNPJ fora
                # do tamanho da coluna, FK, etc.), só esse item é desfeito — a
                # conexão não fica "aborted" pro resto da página (o que faria
                # o item seguinte, e o próprio `registrar` abaixo, falharem em
                # cascata com `InFailedSqlTransaction`).
                async with conn.transaction():
                    if extrair_orgao is not None:
                        orgao = extrair_orgao(item)
                        if orgao is not None:
                            await upsert(conn, "orgaos", "cnpj", orgao)
                    if extrair_fornecedor is not None:
                        fornecedor = extrair_fornecedor(item)
                        if fornecedor is not None:
                            await upsert(conn, "fornecedores", "fornecedor_id", fornecedor)
                    await upsert(conn, tabela, chave, mapear(item))
                gravados += 1
            except Exception as exc:
                falhas += 1
                log.error(
                    "ingest.item_falhou",
                    entidade=entidade,
                    pagina=pagina,
                    erro_tipo=type(exc).__name__,
                )

        total_falhas += falhas
        await registrar(
            conn,
            entidade=entidade,
            modalidade_id=modalidade_id,
            janela=janela,
            pagina=pagina,
            registros_lidos=len(itens),
            registros_gravados=gravados,
            falhas=falhas,
            # Uma página parcialmente persistida continua sinalizada como erro.
            status="ok" if falhas == 0 else "erro",
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
        if not itens or pagina >= total_paginas_esperadas:
            break
        pagina += 1

    if total_falhas:
        raise FalhasIngestao(total_falhas)
