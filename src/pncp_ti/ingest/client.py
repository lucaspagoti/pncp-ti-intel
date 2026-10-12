"""Fábrica do cliente PNCP — reusa `compras_mcp.clients.pncp.PNCPClient` (ADR 0004).

Nenhum cliente HTTP novo para a API do PNCP: só uma instância fina do cliente que o
`compras-mcp` já traz (retry, logging estruturado, paginação validada contra a API
real), apontada para a mesma base pública usada pelo `compras-mcp`.
"""

from __future__ import annotations

from compras_mcp.clients.pncp import PNCPClient

PNCP_BASE_URL = "https://pncp.gov.br/api/consulta"


def criar_cliente() -> PNCPClient:
    return PNCPClient(base_url=PNCP_BASE_URL)
