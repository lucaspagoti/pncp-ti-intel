"""Fábrica do cliente PNCP reusado do compras-mcp (ADR 0004)."""

from __future__ import annotations

from compras_mcp.clients.pncp import PNCPClient

PNCP_BASE_URL = "https://pncp.gov.br/api/consulta"


def criar_cliente() -> PNCPClient:
    return PNCPClient(base_url=PNCP_BASE_URL)
