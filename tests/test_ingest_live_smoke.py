"""Fumaça com rede real: confirma que o shape atual da API do PNCP ainda bate com
os mapeadores (detecta campo renomeado/removido antes de um backfill de horas).

Chama `list_resource` direto (1 página, `tamanho_pagina` mínimo) em vez do loop
completo de `ingerir_janela` — isso é fumaça, não ingestão de verdade; o volume
de `/v1/atas` numa janela de 1 dia já é de centenas de milhares de registros
(ver `docs/adr/`), paginar tudo aqui deixaria `make test` lento demais.

Escreve só no banco de teste (`conn_ingest`), nunca no banco de desenvolvimento.
"""

from __future__ import annotations

from datetime import date, timedelta

from compras_mcp.clients.pncp import PNCPClient

from pncp_ti.db import upsert
from pncp_ti.ingest.client import PNCP_BASE_URL
from pncp_ti.ingest.mapeadores import (
    extrair_fornecedor,
    extrair_orgao,
    extrair_orgao_de_ata,
    mapear_ata,
    mapear_contratacao,
    mapear_contrato,
)

ONTEM = date.today() - timedelta(days=1)
# Pregão Eletrônico nacional sempre tem volume mesmo numa janela curta; 7 dias
# evita cair no quirk do PNCP de responder 204 (corpo vazio) quando uma
# combinação modalidade/janela não tem nenhum resultado.
UMA_SEMANA_ATRAS = date.today() - timedelta(days=7)


async def test_contratacoes_publicacao_ao_vivo(conn_ingest):
    async with PNCPClient(base_url=PNCP_BASE_URL) as cliente:
        resp = await cliente.list_resource(
            "/v1/contratacoes/publicacao",
            pagina=1,
            tamanho_pagina=10,
            dataInicial=UMA_SEMANA_ATRAS.strftime("%Y%m%d"),
            dataFinal=date.today().strftime("%Y%m%d"),
            codigoModalidadeContratacao=6,
        )
    itens = resp.get("data") or []
    assert itens, "esperava pelo menos uma contratação publicada ontem/hoje (modalidade 6)"

    item = itens[0]
    orgao = extrair_orgao(item)
    if orgao is not None:
        await upsert(conn_ingest, "orgaos", "cnpj", orgao)
    await upsert(conn_ingest, "contratacoes", "numero_controle_pncp", mapear_contratacao(item))
    await conn_ingest.commit()

    row = await (
        await conn_ingest.execute(
            "SELECT numero_controle_pncp FROM contratacoes WHERE numero_controle_pncp = %s",
            (item["numeroControlePNCP"],),
        )
    ).fetchone()
    assert row is not None


async def test_atas_ao_vivo(conn_ingest):
    async with PNCPClient(base_url=PNCP_BASE_URL) as cliente:
        resp = await cliente.list_resource(
            "/v1/atas",
            pagina=1,
            tamanho_pagina=10,
            dataInicial=ONTEM.strftime("%Y%m%d"),
            dataFinal=date.today().strftime("%Y%m%d"),
        )
    itens = resp.get("data") or []
    assert itens, "esperava pelo menos uma ata vigente"

    item = itens[0]
    orgao = extrair_orgao_de_ata(item)
    if orgao is not None:
        await upsert(conn_ingest, "orgaos", "cnpj", orgao)
    await upsert(conn_ingest, "atas", "numero_controle_pncp_ata", mapear_ata(item))
    await conn_ingest.commit()

    row = await (
        await conn_ingest.execute(
            "SELECT numero_controle_pncp_ata FROM atas WHERE numero_controle_pncp_ata = %s",
            (item["numeroControlePNCPAta"],),
        )
    ).fetchone()
    assert row is not None


async def test_contratos_ao_vivo(conn_ingest):
    async with PNCPClient(base_url=PNCP_BASE_URL) as cliente:
        resp = await cliente.list_resource(
            "/v1/contratos",
            pagina=1,
            tamanho_pagina=10,
            dataInicial=ONTEM.strftime("%Y%m%d"),
            dataFinal=date.today().strftime("%Y%m%d"),
        )
    itens = resp.get("data") or []
    assert itens, "esperava pelo menos um contrato publicado ontem/hoje"

    item = itens[0]
    orgao = extrair_orgao(item)
    if orgao is not None:
        await upsert(conn_ingest, "orgaos", "cnpj", orgao)
    fornecedor = extrair_fornecedor(item)
    if fornecedor is not None:
        await upsert(conn_ingest, "fornecedores", "ni", fornecedor)
    await upsert(conn_ingest, "contratos", "numero_controle_pncp", mapear_contrato(item))
    await conn_ingest.commit()

    row = await (
        await conn_ingest.execute(
            "SELECT numero_controle_pncp FROM contratos WHERE numero_controle_pncp = %s",
            (item["numeroControlePNCP"],),
        )
    ).fetchone()
    assert row is not None
