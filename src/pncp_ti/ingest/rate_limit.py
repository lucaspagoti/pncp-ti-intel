"""Limitador de taxa proativo para chamadas ao PNCP.

O `BaseAsyncClient` do `compras-mcp` (reusado via ADR 0004) já trata retry reativo em
429/5xx, mas não limita a taxa de saída antes de bater no rate limit. Isso aqui é
puramente para sermos bons vizinhos da API pública (risco "bloqueio pelo WAF" do
`docs/PLANO.md`), não uma garantia de nunca receber 429 — o retry do cliente continua
sendo a rede de segurança.
"""

from __future__ import annotations

import asyncio
import time


class LimitadorTaxa:
    def __init__(self, requisicoes_por_segundo: float) -> None:
        if requisicoes_por_segundo <= 0:
            raise ValueError("requisicoes_por_segundo deve ser positivo")
        self._intervalo_minimo = 1.0 / requisicoes_por_segundo
        self._ultima_chamada: float | None = None

    async def aguardar(self) -> None:
        agora = time.monotonic()
        if self._ultima_chamada is not None:
            faltante = self._intervalo_minimo - (agora - self._ultima_chamada)
            if faltante > 0:
                await asyncio.sleep(faltante)
        self._ultima_chamada = time.monotonic()
