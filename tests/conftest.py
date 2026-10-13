"""Fixtures compartilhadas pelos testes do pncp-ti.

Os testes aqui sobem o `compras-mcp` real (via `uv run`, stdio) — nada é mockado.
Isso cobre o critério de aceite da Fase 0 ("Claude responde usando o compras-mcp
local") e detecta mudanças no servidor de terceiro (ADR 0002, "rug pull").
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from psycopg import sql
from psycopg.rows import dict_row

from pncp_ti.config import admin_dsn, get_settings, ingest_dsn, reader_dsn

os.environ.setdefault("PNCP_TI_IDENTITY_KEY", "synthetic-test-key-32-characters-minimum")

REPO_ROOT = Path(__file__).parent.parent


def compras_mcp_transport() -> StdioTransport:
    """Mesmo comando registrado em `.mcp.json`, para os dois ficarem sempre em sincronia.

    Usa `uv run` (não `uvx --from`) para rodar a versão travada no `uv.lock` com
    hashes — protege a árvore de dependências transitiva, não só o pacote
    top-level (ADR 0002, defesa contra "rug pull").
    """
    return StdioTransport(
        command="uv",
        args=["run", "--project", str(Path(__file__).parent.parent), "compras-mcp"],
        env={
            "TRANSPARENCIA_API_KEY": "",
            "INCLUIR_CPF_COMPLETO": "false",
            "LOG_LEVEL": "ERROR",
        },
    )


@pytest.fixture
async def compras_mcp_client():
    async with Client(compras_mcp_transport()) as client:
        yield client


@pytest.fixture(scope="session")
def nome_banco_teste() -> str:
    """Banco Postgres dedicado aos testes — nunca o banco de desenvolvimento.

    Recriado do zero e migrado via Alembic a cada sessão de testes; descartado
    ao final. Evita que fixtures de teste sujem dados reais de ingestão.
    """
    settings = get_settings()
    nome = f"pncp_test_{uuid4().hex}"
    dsn_manutencao = admin_dsn(replace(settings, postgres_db="postgres"))
    with psycopg.connect(dsn_manutencao, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))

    env = os.environ.copy()
    env["POSTGRES_DB"] = nome
    try:
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            check=True,
            env=env,
            cwd=REPO_ROOT,
        )
        yield nome
    finally:
        with psycopg.connect(dsn_manutencao, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


@pytest.fixture
async def conn_ingest(nome_banco_teste: str):
    """Conexão async com o papel `ingest`, apontada para o banco de teste."""
    settings = get_settings()
    dsn = ingest_dsn(replace(settings, postgres_db=nome_banco_teste))
    conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
    # Cada teste começa isolado; este DSN sempre aponta para o banco UUID efêmero.
    await conn.execute("DELETE FROM snapshots_atas_ti")
    await conn.execute("DELETE FROM orgaos")
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
async def conn_reader(nome_banco_teste: str):
    """Conexão somente leitura, apontada para a view do banco de teste."""
    settings = get_settings()
    dsn = reader_dsn(replace(settings, postgres_db=nome_banco_teste))
    conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
    yield conn
    await conn.close()
