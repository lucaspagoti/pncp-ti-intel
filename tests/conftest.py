"""Fixtures compartilhadas pelos testes do pncp-ti.

Os testes aqui sobem o `compras-mcp` real (via `uvx`, stdio) — nada é mockado.
Isso cobre o critério de aceite da Fase 0 ("Claude responde usando o compras-mcp
local") e detecta mudanças no servidor de terceiro (ADR 0002, "rug pull").
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from psycopg.rows import dict_row

from pncp_ti.config import get_settings

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
    nome = f"{settings.postgres_db}_test"
    dsn_manutencao = (
        f"postgresql://postgres:{settings.postgres_admin_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres"
    )
    with psycopg.connect(dsn_manutencao, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {nome}")

    env = os.environ.copy()
    env["POSTGRES_DB"] = nome
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        cwd=REPO_ROOT,
    )

    yield nome

    with psycopg.connect(dsn_manutencao, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")


@pytest.fixture
async def conn_ingest(nome_banco_teste: str):
    """Conexão async com o papel `ingest`, apontada para o banco de teste."""
    settings = get_settings()
    dsn = (
        f"postgresql://ingest:{settings.ingest_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{nome_banco_teste}"
    )
    conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
    yield conn
    await conn.close()
