"""Teste de fumaça: o compras-mcp local responde a uma pergunta real.

Cobre o critério de aceite da Fase 0 ("Claude responde 'quais atas vigentes de
outsourcing de impressão existem?' usando o compras-mcp local") — mas só a parte
de **plumbing**: prova que a tool roda, filtra por vigência e devolve dados reais
e bem formados do PNCP.

O que este teste **não** prova: que os resultados são, de fato, contratos de
*outsourcing* de impressão. A busca por palavra-chave do compras-mcp é um filtro
léxico (acha "papel para impressão", "plotagem com impressão digital" etc. junto
com outsourcing de verdade) — distinguir isso é trabalho do classificador de TI
da Fase 3 (ADR 0006), não da Fase 0. A demonstração qualificada (interpretar os
resultados, separar outsourcing real de falso positivo) fica para quando o Lucas
fizer a pergunta de verdade no chat do Claude Code, com o `.mcp.json` carregado.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import date, timedelta

PALAVRA_CHAVE = "impressao"


def _sem_acento(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


async def test_arp_buscar_por_objeto_outsourcing_impressao(compras_mcp_client):
    hoje = date.today()
    data_min = hoje.isoformat()
    data_max = (hoje + timedelta(days=365)).isoformat()

    resultado = await compras_mcp_client.call_tool(
        "compras_arp_buscar_por_objeto",
        {
            "palavra_chave": PALAVRA_CHAVE,
            "data_vigencia_final_min": data_min,
            "data_vigencia_final_max": data_max,
            "max_paginas_varridas": 10,
            "max_resultados": 20,
        },
    )

    payload = resultado.structured_content or json.loads(resultado.content[0].text)

    assert "resultado" in payload
    assert "total_examinadas" in payload
    assert payload["total_examinadas"] > 0, "compras-mcp não varreu nenhuma ARP — API indisponível?"

    itens = payload["resultado"]
    assert itens, (
        f"Nenhuma ARP vigente com '{PALAVRA_CHAVE}' no objeto entre {data_min} e {data_max}. "
        "Pode ser sazonal — se persistir, investigar antes de aceitar a fase."
    )

    # Contrato estrutural: cada item precisa ter os campos que o restante do
    # projeto (e a demonstração manual) depende para responder com fonte.
    campos_esperados = {
        "objeto",
        "nomeOrgao",
        "numeroAtaRegistroPreco",
        "linkAtaPNCP",
        "dataVigenciaFinal",
    }
    for item in itens:
        faltando = campos_esperados - item.keys()
        assert not faltando, f"Item sem campos esperados ({faltando}): {item}"

        # O filtro léxico do compras-mcp é client-side; confere que de fato
        # respeitou a palavra-chave (normalizando acento) e a janela de vigência.
        assert _sem_acento(PALAVRA_CHAVE) in _sem_acento(item["objeto"]), item["objeto"]
        assert data_min <= item["dataVigenciaFinal"] <= data_max, item["dataVigenciaFinal"]
        assert item["linkAtaPNCP"].startswith("https://pncp.gov.br/"), item["linkAtaPNCP"]
