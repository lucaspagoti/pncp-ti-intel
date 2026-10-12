"""Snapshot das tools do `compras-mcp`.

Falha se qualquer tool mudar de nome, descrição ou schema de parâmetros, ou se a
contagem total mudar — defesa contra "rug pull" num componente de terceiro
(ADR 0002, seção de Segurança do `docs/PLANO.md`).

Para atualizar o snapshot depois de confirmar uma mudança legítima de versão do
`compras-mcp` (ler o changelog e o diff antes, por regra do CLAUDE.md):

    uv run python tests/test_compras_mcp_snapshot.py --update
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "compras_mcp_tools.json"


def _tool_to_dict(tool) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.inputSchema,
    }


async def _fetch_tools_snapshot() -> list[dict]:
    from conftest import compras_mcp_transport
    from fastmcp import Client

    async with Client(compras_mcp_transport()) as client:
        tools = await client.list_tools()
    return sorted((_tool_to_dict(t) for t in tools), key=lambda t: t["name"])


async def test_compras_mcp_tools_match_snapshot():
    if not SNAPSHOT_PATH.exists():
        pytest.fail(
            f"Snapshot ausente em {SNAPSHOT_PATH}. Gere com: "
            "uv run python tests/test_compras_mcp_snapshot.py --update"
        )

    current = await _fetch_tools_snapshot()
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    current_names = {t["name"] for t in current}
    expected_names = {t["name"] for t in expected}

    assert current_names == expected_names, (
        f"Tools adicionadas: {current_names - expected_names} | "
        f"Tools removidas: {expected_names - current_names}"
    )
    assert current == expected, (
        "Descrição ou schema de alguma tool do compras-mcp mudou. "
        "Confirme se é uma mudança de versão esperada antes de atualizar o snapshot."
    )


async def _update_snapshot() -> None:
    tools = await _fetch_tools_snapshot()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(tools, indent=2, ensure_ascii=False) + "\n"
    SNAPSHOT_PATH.write_text(text, encoding="utf-8")
    print(f"Snapshot atualizado: {len(tools)} tools em {SNAPSHOT_PATH}")


if __name__ == "__main__":
    import asyncio

    if "--update" in sys.argv:
        asyncio.run(_update_snapshot())
    else:
        print("Uso: uv run python tests/test_compras_mcp_snapshot.py --update")
