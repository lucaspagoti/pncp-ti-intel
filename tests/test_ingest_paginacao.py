"""Contratos do envelope PNCP e retry, sem consultas externas."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from compras_mcp.errors import ComprasHTTPError, ComprasRateLimitError

from pncp_ti.ingest import executar
from pncp_ti.ingest.windows import Janela


@pytest.mark.parametrize(
    "resposta,pagina",
    [
        (None, 1),
        ({}, 1),
        ({"data": None, "totalPaginas": 1}, 1),
        ({"data": [1], "totalPaginas": 1}, 1),
        ({"data": [], "totalPaginas": "1"}, 1),
        ({"data": [], "totalPaginas": True}, 1),
        ({"data": [], "totalPaginas": -1}, 1),
        ({"data": [{}], "totalPaginas": 0}, 1),
        ({"data": [], "totalPaginas": 1}, 1),
        ({"data": [], "totalPaginas": 0}, 2),
        ({"data": [{}], "totalPaginas": 1}, 2),
        ({"data": [{}], "totalPaginas": 1, "numeroPagina": 2}, 1),
    ],
)
def test_envelope_invalido_nao_encerra_carga_com_sucesso(resposta, pagina):
    with pytest.raises(ValueError):
        executar._validar_pagina(resposta, pagina)


async def test_204_inicial_e_json_corrompido_sao_distintos():
    cliente = AsyncMock()
    cliente.list_resource.side_effect = ComprasHTTPError("Resposta nao-JSON de pncp/v1/atas: ")
    janela = Janela(date(2026, 1, 1), date(2026, 1, 1))
    resposta = await executar._buscar_pagina(
        cliente, "/v1/atas", pagina=1, janela=janela, filtros={}
    )
    assert executar._validar_pagina(resposta) == ([], 0)
    cliente.list_resource.side_effect = ComprasHTTPError(
        'Resposta nao-JSON de pncp/v1/atas: {"data":'
    )
    with pytest.raises(ComprasHTTPError):
        await executar._buscar_pagina(cliente, "/v1/atas", pagina=1, janela=janela, filtros={})


async def test_retry_preserva_pagina_e_filtros(monkeypatch):
    pausa = AsyncMock()
    monkeypatch.setattr(executar.asyncio, "sleep", pausa)
    cliente = AsyncMock()
    resposta = {"data": [{"id": "sintetico"}], "totalPaginas": 2}
    cliente.list_resource.side_effect = [ComprasRateLimitError("429"), resposta]
    janela = Janela(date(2026, 1, 1), date(2026, 1, 1))
    assert (
        await executar._buscar_pagina(cliente, "/v1/atas", pagina=2, janela=janela, filtros={})
        == resposta
    )
    assert cliente.list_resource.await_args_list[0] == cliente.list_resource.await_args_list[1]
    pausa.assert_awaited_once_with(executar.BACKOFF_INICIAL_SEGUNDOS)


async def test_retry_cobre_http_generico_transitorio_sem_repetir_404(monkeypatch):
    pausa = AsyncMock()
    monkeypatch.setattr(executar.asyncio, "sleep", pausa)
    cliente = AsyncMock()
    resposta = {"data": [{"id": "sintetico"}], "totalPaginas": 1}
    cliente.list_resource.side_effect = [
        ComprasHTTPError("pncp/v1/atas respondeu 403: gateway"),
        resposta,
    ]
    janela = Janela(date(2026, 1, 1), date(2026, 1, 1))

    assert (
        await executar._buscar_pagina(cliente, "/v1/atas", pagina=1, janela=janela, filtros={})
        == resposta
    )
    pausa.assert_awaited_once_with(executar.BACKOFF_INICIAL_SEGUNDOS)

    cliente.list_resource.reset_mock()
    cliente.list_resource.side_effect = ComprasHTTPError("pncp/v1/atas respondeu 404: ausente")
    with pytest.raises(ComprasHTTPError):
        await executar._buscar_pagina(cliente, "/v1/atas", pagina=1, janela=janela, filtros={})
    cliente.list_resource.assert_awaited_once()
