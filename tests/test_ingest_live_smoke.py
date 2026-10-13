"""Fumaça leve da listagem de atas PNCP, sem persistir conteúdo da fonte."""

from datetime import date

from compras_mcp.clients.pncp import PNCPClient

from pncp_ti.classificar.regra import objeto_ata_tem_sinal_ti
from pncp_ti.ingest.client import PNCP_BASE_URL
from pncp_ti.ingest.executar import _validar_pagina


async def test_listagem_de_atas_vigentes_ao_vivo():
    hoje = date.today().strftime("%Y%m%d")
    async with PNCPClient(base_url=PNCP_BASE_URL) as cliente:
        resposta = await cliente.list_resource(
            "/v1/atas",
            pagina=1,
            tamanho_pagina=10,
            dataInicial=hoje,
            dataFinal=hoje,
        )
    atas, total = _validar_pagina(resposta)
    assert total >= 1
    assert atas
    assert "numeroControlePNCPAta" in atas[0]
    assert isinstance(objeto_ata_tem_sinal_ti(atas[0].get("objetoContratacao")), bool)
