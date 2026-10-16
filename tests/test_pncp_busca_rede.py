"""Contrato real da busca PNCP (R3). Opcional: roda só com PNCP_TI_TESTES_REDE=1.

A API não é documentada; este teste falha alto se o envelope ou os campos que a carga lê
mudarem. Não roda no CI (rede externa e instável).
"""

from __future__ import annotations

import os
from datetime import date

import httpx
import pytest

from pncp_ti.fontes import pncp_busca as b

pytestmark = [
    pytest.mark.rede,
    pytest.mark.skipif(
        os.environ.get("PNCP_TI_TESTES_REDE") != "1", reason="defina PNCP_TI_TESTES_REDE=1"
    ),
]


async def test_busca_real_mantem_o_contrato_lido_pela_carga():
    async with httpx.AsyncClient(timeout=30, headers={"Accept": "application/json"}) as c:
        itens, total = await b.buscar_termo(c, b.LimitadorTaxa(2), "switch")
    assert total > 0 and len(itens) == min(total, b.LIMITE_JANELA)
    # validar_pagina já exige os campos mínimos; aqui confere o que o mapeamento usa.
    atas = [a for i in itens if (a := b.mapear(i, "switch", date.today()))]
    assert atas, "nenhuma ata vigente mapeada: o formato mudou?"
    assert all(a.link_origem.startswith("https://pncp.gov.br/app/atas/") for a in atas)
    assert any(b.casa_termo(a.objeto, "switch") for a in atas)
