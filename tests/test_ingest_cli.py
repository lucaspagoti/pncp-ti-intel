"""CLI da ingestão: somente snapshot diário, sem modo histórico."""

import sys
from contextlib import asynccontextmanager
from datetime import UTC, date
from unittest.mock import AsyncMock

import pytest

from pncp_ti.ingest import cli


def test_cli_rejeita_argumento_de_backfill(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ingest", "--backfill"])
    with pytest.raises(SystemExit):
        cli._parse_args()


async def test_rodar_chama_snapshot_com_data_de_referencia(monkeypatch):
    conn = AsyncMock()
    monkeypatch.setattr(cli, "get_settings", lambda: type("S", (), {"requests_per_second": 7})())
    monkeypatch.setattr(cli, "conectar", AsyncMock(return_value=conn))
    ingest = AsyncMock()
    monkeypatch.setattr(cli, "ingerir_snapshot", ingest)

    @asynccontextmanager
    async def cliente():
        yield object()

    monkeypatch.setattr(cli, "criar_cliente", cliente)
    referencia = date(2026, 10, 12)
    await cli._rodar(referencia)

    assert ingest.await_args.args[0] is conn
    assert ingest.await_args.args[3] == referencia
    conn.close.assert_awaited_once()


def test_cli_usa_dia_de_brasilia_na_virada_utc(monkeypatch):
    from datetime import datetime

    class RelogioFixo:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 13, 1, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(cli, "datetime", RelogioFixo)
    monkeypatch.setattr(sys, "argv", ["ingest", "--diario"])
    rodar = AsyncMock()
    monkeypatch.setattr(cli, "_rodar", rodar)
    cli.main()
    rodar.assert_awaited_once_with(date(2026, 10, 12))
