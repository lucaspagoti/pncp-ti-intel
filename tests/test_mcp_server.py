"""Tools MCP: consultas fixas, validação e protocolo stdio sem rede ou banco real."""

import os
from datetime import timedelta
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from pncp_ti import mcp_server as server


async def test_mcp_usa_parametros_e_busca_literal(monkeypatch):
    chamadas = []

    async def consultar(sql, params):
        chamadas.append((sql, params))
        return []

    monkeypatch.setattr(server, "consultar", consultar)
    termo = "'; DROP TABLE atas; --_%"
    assert await server.buscar_atas(termo, "siga_rj") == []
    assert chamadas[0][0] == server.BUSCAR
    assert termo not in chamadas[0][0]
    assert chamadas[0][1]["termo"].endswith(r"\_\%%")
    await server.itens_ata("siga_rj", "'; SQL", 10, 20)
    assert chamadas[1] == (
        server.ITENS,
        dict(fonte="siga_rj", id_ata="'; SQL", limite=10, offset=20),
    )
    await server.consumo_ata("siga_rj", "1")
    assert chamadas[2][0] == server.CONSUMO


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(termo=""),
        dict(termo="x" * 201),
        dict(termo="x", fonte="bad"),
        dict(termo="x", limite=101),
        dict(termo="x", limite=0),
        dict(termo="x", offset=-1),
        dict(termo="x", offset=10001),
    ],
)
async def test_mcp_recusa_entradas_invalidas(kwargs):
    with pytest.raises(ValueError):
        await server.buscar_atas(**kwargs)


async def test_mcp_stdio_handshake_e_tools():
    root = Path(__file__).resolve().parents[1]
    parametros = StdioServerParameters(
        command=str(root / ".venv/bin/python"),
        args=["-m", "pncp_ti.mcp_server"],
        env=os.environ | {"PYTHONPATH": str(root / "src")},
        cwd=str(root),
    )
    async with stdio_client(parametros) as (reader, writer):
        async with ClientSession(
            reader, writer, read_timeout_seconds=timedelta(seconds=10)
        ) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            assert {t.name for t in tools} == {"buscar_atas", "itens_ata", "consumo_ata"}
            assert all("sql" not in t.inputSchema.get("properties", {}) for t in tools)
            resultado = await session.call_tool("buscar_atas", {"termo": ""})
            assert resultado.isError
