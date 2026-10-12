"""Teste de fumaça: o compras-mcp local responde a uma pergunta real.

Cobre o critério de aceite da Fase 0 ("Claude responde 'quais atas vigentes de
outsourcing de impressão existem?' usando o compras-mcp local") de forma
automatizada. A demonstração manual no chat, para o Lucas, usa a mesma tool.
"""

from __future__ import annotations

import json
from datetime import date, timedelta


async def test_arp_buscar_por_objeto_outsourcing_impressao(compras_mcp_client):
    hoje = date.today()
    resultado = await compras_mcp_client.call_tool(
        "compras_arp_buscar_por_objeto",
        {
            "palavra_chave": "impressao",
            "data_vigencia_final_min": hoje.isoformat(),
            "data_vigencia_final_max": (hoje + timedelta(days=365)).isoformat(),
            "max_paginas_varridas": 10,
            "max_resultados": 20,
        },
    )

    payload = resultado.structured_content or json.loads(resultado.content[0].text)

    assert "resultado" in payload
    assert "total_examinadas" in payload
    assert payload["total_examinadas"] > 0, "compras-mcp não varreu nenhuma ARP — API indisponível?"
