"""Executa o snapshot diário de atas de TI vigentes (ADR 0015)."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import structlog

from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.ingest.atas import ingerir_snapshot
from pncp_ti.ingest.client import criar_cliente
from pncp_ti.ingest.rate_limit import LimitadorTaxa

log = structlog.get_logger(__name__)
FUSO_PNCP = ZoneInfo("America/Sao_Paulo")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Snapshot diário das atas de TI vigentes.")
    parser.add_argument(
        "--diario",
        action="store_true",
        help="opção explícita; sem opções históricas ou backfill (ADR 0015).",
    )
    return parser.parse_args()


async def _rodar(referencia: date) -> None:
    settings = get_settings()
    conn = await conectar(settings)
    try:
        async with criar_cliente() as cliente:
            await ingerir_snapshot(
                conn,
                cliente,
                LimitadorTaxa(settings.requests_per_second),
                referencia,
            )
    finally:
        await conn.close()


def main() -> None:
    _parse_args()
    try:
        asyncio.run(_rodar(datetime.now(FUSO_PNCP).date()))
    except Exception as exc:
        log.error("atas.snapshot_falhou", erro_tipo=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
