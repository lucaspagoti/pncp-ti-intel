"""R3 → R6: o total por termo que a busca PNCP grava é o que o alerta da operação lê."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx

from pncp_ti.fontes import pncp_busca as b
from pncp_ti.operacao import SP, alertas

HOJE = date(2026, 10, 16)
AGORA = datetime(2026, 10, 16, 8, 30, tzinfo=SP)


def carga(fonte: str, contagens: dict | None = None) -> dict:
    instante = AGORA - timedelta(hours=1)
    return dict(
        fonte=fonte,
        iniciado_em=instante,
        concluido_em=instante,
        status="concluida",
        ativa=True,
        data_referencia=instante.date(),
        geracao={"atas": {"last_modified": instante.isoformat()}},
        # Gancho R3 sobre as contagens da busca; o coletor oficial grava as mesmas chaves.
        contagens={**(contagens or {}), "coletor": "api_consulta"} if fonte == "pncp_busca" else {},
    )


async def _coletar(respostas: dict[str, list[dict]]) -> b.Coleta:
    def tratar(req: httpx.Request) -> httpx.Response:
        itens = respostas.get(req.url.params["q"], [])
        return httpx.Response(200, json={"items": itens, "total": len(itens)})

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        return await b.coletar(list(respostas), HOJE, c)


async def test_termo_estavel_zerado_dispara_o_alerta_e_com_resultado_nao():
    base = [carga("siga_rj"), carga("compras_arp")]
    ok = await _coletar({"notebook": [{**_ITEM}]})
    zerado = await _coletar({"notebook": []})
    avisos_ok = alertas([*base, carga("pncp_busca", ok.contagens)], AGORA, "notebook")
    avisos_zero = alertas([*base, carga("pncp_busca", zerado.contagens)], AGORA, "notebook")
    assert avisos_ok == []
    assert [codigo for codigo, _ in avisos_zero] == ["pncp:zero"]


_ITEM = {
    "numero_controle_pncp": "00394502000144-1-009124/2026-000001",
    "title": "Ata nº 1/2026",
    "description": "Aquisição de notebook",
    "item_url": "/atas/00394502000144/2026/9124/1",
    "orgao_nome": "ORGAO",
    "data_fim_vigencia": "2027-09-02",
}
