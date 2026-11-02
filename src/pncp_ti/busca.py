"""Atualização da busca materializada da web depois de cada carga (ADR 0035).

A troca de carga já é atômica; `mv_busca_atas` só passa a refletir a carga nova quando o
refresh termina. O `CONCURRENTLY` não bloqueia as buscas em andamento. Se o refresh falhar, a
carga continua publicada e a web segue com a busca anterior, que é consistente.

    python -m pncp_ti.busca   # refresh manual (make refresh-busca)
"""

from __future__ import annotations

import asyncio
import time

import psycopg
import structlog

from pncp_ti.config import get_settings
from pncp_ti.db import conectar

log = structlog.get_logger()


async def atualizar_busca(conn: psycopg.AsyncConnection) -> bool:
    """Refresh da MV; devolve False e registra o erro em vez de propagar.

    Exige a conexão fora de transação: o rollback de um refresh que falha não pode levar junto
    uma publicação ainda não commitada.
    """
    if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        raise RuntimeError("atualizar_busca chamada com transação aberta; publique antes")
    inicio = time.monotonic()
    try:
        await conn.execute("SELECT atualizar_busca()")
        await conn.commit()
    except psycopg.Error as exc:
        await conn.rollback()
        log.error("busca_refresh_falhou", tipo=type(exc).__name__, sqlstate=exc.sqlstate)
        return False
    log.info("busca_atualizada", segundos=round(time.monotonic() - inicio, 1))
    return True


async def principal() -> int:
    conn = await conectar(get_settings())
    try:
        return 0 if await atualizar_busca(conn) else 1
    finally:
        await conn.close()


def main() -> None:
    raise SystemExit(asyncio.run(principal()))


if __name__ == "__main__":
    main()
