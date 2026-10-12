"""Fixtures compartilhadas pelos testes do pncp-ti.

Os testes aqui sobem o `compras-mcp` real (via `uvx`, stdio) — nada é mockado.
Isso cobre o critério de aceite da Fase 0 ("Claude responde usando o compras-mcp
local") e detecta mudanças no servidor de terceiro (ADR 0002, "rug pull").
"""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

COMPRAS_MCP_VERSION = "0.4.0"


def compras_mcp_transport() -> StdioTransport:
    """Mesmo comando registrado em `.mcp.json`, para os dois ficarem sempre em sincronia."""
    return StdioTransport(
        command="uvx",
        args=["--from", f"compras-mcp=={COMPRAS_MCP_VERSION}", "compras-mcp"],
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
