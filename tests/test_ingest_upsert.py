"""Idempotência da ingestão (ADR 0005): mesma janela processada duas vezes deve
gerar as mesmas contagens — critério de aceite da Fase 1. Usa um cliente PNCP
falso (sem rede) contra um Postgres de teste real (sem mockar o banco).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from compras_mcp.errors import ComprasHTTPError

from pncp_ti.ingest.executar import FalhasIngestao, _validar_pagina, ingerir_janela
from pncp_ti.ingest.mapeadores import extrair_orgao, mapear_contratacao
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import Janela

CONTRATACAO_1: dict[str, Any] = {
    "numeroControlePNCP": "01612441000107-1-000156/2026",
    "orgaoEntidade": {
        "cnpj": "01612441000107",
        "razaoSocial": "MUNICIPIO DE BELA VISTA DO CAROBA",
        "poderId": "N",
        "esferaId": "M",
    },
    "unidadeOrgao": {
        "ufSigla": "PR",
        "municipioNome": "Bela Vista da Caroba",
        "codigoUnidade": "1",
        "nomeUnidade": "Prefeitura Municipal de Bela Vista da Caroba",
        "codigoIbge": "4102752",
    },
    "anoCompra": 2026,
    "srp": False,
    "sequencialCompra": 156,
    "numeroCompra": "PR66",
    "processo": "PR66/2026",
    "objetoCompra": "Aquisição de materiais elétricos.",
    "modalidadeId": 6,
    "modalidadeNome": "Pregão - Eletrônico",
    "situacaoCompraId": 1,
    "situacaoCompraNome": "Divulgada no PNCP",
    "valorTotalEstimado": 20901.1,
    "valorTotalHomologado": None,
    "dataPublicacaoPncp": "2026-10-01T00:01:07",
    "dataInclusao": "2026-10-01T00:01:07",
    "dataAtualizacao": "2026-10-01T00:01:07",
    "dataAtualizacaoGlobal": "2026-10-01T00:01:24",
    "dataAberturaProposta": "2026-09-28T08:00:01",
    "dataEncerramentoProposta": "2026-10-08T08:00:01",
    "linkSistemaOrigem": None,
    "linkProcessoEletronico": None,
}

CONTRATACAO_2: dict[str, Any] = {
    **CONTRATACAO_1,
    "numeroControlePNCP": "01612441000107-1-000157/2026",
}


class ClientePNCPFalso:
    """Paginação fixa, sem rede — não dá pra usar o `PNCPClient` real num teste
    de idempotência determinístico (a API muda a cada chamada)."""

    def __init__(self, paginas: dict[int, dict[str, Any]], total_paginas: int = 1) -> None:
        self._paginas = paginas
        self._total_paginas = total_paginas

    async def list_resource(self, path: str, *, pagina: int, **_kwargs: Any) -> dict[str, Any]:
        if pagina in self._paginas:
            return {"data": self._paginas[pagina], "totalPaginas": self._total_paginas}
        return {"data": [], "totalPaginas": self._total_paginas}


async def test_mesma_janela_processada_duas_vezes_mesma_contagem(conn_ingest):
    cliente = ClientePNCPFalso({1: [CONTRATACAO_1, CONTRATACAO_2]})
    limitador = LimitadorTaxa(1000)
    janela = Janela(inicio=date(2026, 10, 1), fim=date(2026, 10, 10))

    chaves = [CONTRATACAO_1["numeroControlePNCP"], CONTRATACAO_2["numeroControlePNCP"]]

    async def contar() -> int:
        # O banco de teste é compartilhado pela sessão (ver `conftest.py`) — conta
        # só as chaves desta fixture, não a tabela inteira, pra não se misturar
        # com linhas de outros testes (ex.: a fumaça com rede real).
        row = await (
            await conn_ingest.execute(
                "SELECT count(*) AS n FROM contratacoes WHERE numero_controle_pncp = ANY(%s)",
                (chaves,),
            )
        ).fetchone()
        return row["n"]

    async def rodar() -> None:
        await ingerir_janela(
            conn_ingest,
            cliente,
            limitador,
            entidade="contratacoes_teste",
            tabela="contratacoes",
            chave="numero_controle_pncp",
            path="/v1/contratacoes/publicacao",
            janela=janela,
            filtros={"codigoModalidadeContratacao": 6},
            mapear=mapear_contratacao,
            modalidade_id=6,
            extrair_orgao=extrair_orgao,
        )

    await rodar()
    primeira_contagem = await contar()
    assert primeira_contagem == 2

    await rodar()
    cliente._paginas[1][0] = {**CONTRATACAO_1, "objetoCompra": "Objeto atualizado"}
    await rodar()
    row = await (
        await conn_ingest.execute(
            "SELECT objeto_compra FROM contratacoes WHERE numero_controle_pncp = %s",
            (CONTRATACAO_1["numeroControlePNCP"],),
        )
    ).fetchone()
    assert row["objeto_compra"] == "Objeto atualizado"
    segunda_contagem = await contar()
    assert segunda_contagem == primeira_contagem

    log_rows = await (
        await conn_ingest.execute(
            "SELECT count(*) AS n FROM log_execucao_ingestao "
            "WHERE entidade = 'contratacoes_teste' AND status = 'ok'"
        )
    ).fetchone()
    assert log_rows["n"] >= 1

    # `--forcar` reprocessa uma janela já marcada `ok` de propósito (ex.: depois
    # de corrigir um mapeador) — não pode bater em UniqueViolation no log.
    await ingerir_janela(
        conn_ingest,
        cliente,
        limitador,
        entidade="contratacoes_teste",
        tabela="contratacoes",
        chave="numero_controle_pncp",
        path="/v1/contratacoes/publicacao",
        janela=janela,
        filtros={"codigoModalidadeContratacao": 6},
        mapear=mapear_contratacao,
        modalidade_id=6,
        extrair_orgao=extrair_orgao,
        forcar=True,
    )
    assert await contar() == primeira_contagem


async def test_item_com_erro_nao_derruba_os_outros_itens_da_pagina(conn_ingest):
    # Savepoint por item (executar.py): um item sem "numeroControlePNCP" quebra
    # mapear_contratacao com KeyError, mas isso não pode "envenenar" a conexão
    # e impedir o upsert do item seguinte na mesma página (bug real: sem
    # savepoint, o segundo upsert falhava com InFailedSqlTransaction).
    item_ruim: dict[str, Any] = {"objetoCompra": "sem numeroControlePNCP"}
    cliente = ClientePNCPFalso({1: [item_ruim, CONTRATACAO_1]})
    limitador = LimitadorTaxa(1000)
    janela = Janela(inicio=date(2026, 11, 1), fim=date(2026, 11, 10))

    with pytest.raises(FalhasIngestao, match="1 falha"):
        await ingerir_janela(
            conn_ingest,
            cliente,
            limitador,
            entidade="contratacoes_teste_item_ruim",
            tabela="contratacoes",
            chave="numero_controle_pncp",
            path="/v1/contratacoes/publicacao",
            janela=janela,
            filtros={"codigoModalidadeContratacao": 6},
            mapear=mapear_contratacao,
            modalidade_id=6,
            extrair_orgao=extrair_orgao,
        )

    linha_boa = await (
        await conn_ingest.execute(
            "SELECT 1 FROM contratacoes WHERE numero_controle_pncp = %s",
            (CONTRATACAO_1["numeroControlePNCP"],),
        )
    ).fetchone()
    assert linha_boa is not None, "o item válido depois do item ruim devia ter sido gravado"

    log_row = await (
        await conn_ingest.execute(
            "SELECT status, falhas, registros_gravados FROM log_execucao_ingestao "
            "WHERE entidade = 'contratacoes_teste_item_ruim'"
        )
    ).fetchone()
    assert log_row["falhas"] == 1
    assert log_row["registros_gravados"] == 1
    # Página com falha não pode ficar marcada "ok" — senão o próximo run (sem
    # --forcar) pula ela pra sempre e o item ruim nunca é revisitado.
    assert log_row["status"] == "erro"


class ClientePNCP204Falso:
    """Simula o quirk real do PNCP: combinação sem resultado responde 204 com
    corpo vazio, e o `BaseAsyncClient` reusado levanta `ComprasHTTPError` ao
    tentar decodificar JSON (confirmado por chamada real nesta sessão)."""

    async def list_resource(self, path: str, *, pagina: int, **_kwargs: Any) -> dict[str, Any]:
        raise ComprasHTTPError(f"Resposta nao-JSON de pncp{path}: ")


async def test_janela_sem_resultado_204_nao_quebra_a_ingestao(conn_ingest):
    cliente = ClientePNCP204Falso()
    limitador = LimitadorTaxa(1000)
    janela = Janela(inicio=date(2026, 10, 1), fim=date(2026, 10, 10))

    await ingerir_janela(
        conn_ingest,
        cliente,
        limitador,
        entidade="contratacoes_teste_204",
        tabela="contratacoes",
        chave="numero_controle_pncp",
        path="/v1/contratacoes/publicacao",
        janela=janela,
        filtros={"codigoModalidadeContratacao": 13},
        mapear=mapear_contratacao,
        modalidade_id=13,
        extrair_orgao=extrair_orgao,
    )

    log_row = await (
        await conn_ingest.execute(
            "SELECT status, registros_lidos FROM log_execucao_ingestao "
            "WHERE entidade = 'contratacoes_teste_204'"
        )
    ).fetchone()
    assert log_row["status"] == "ok"
    assert log_row["registros_lidos"] == 0


@pytest.mark.parametrize(
    "resp",
    [
        None,
        {},
        {"data": None, "totalPaginas": 1},
        {"data": {}, "totalPaginas": 1},
        {"data": [1], "totalPaginas": 1},
        {"data": [], "totalPaginas": "1"},
        {"data": [], "totalPaginas": True},
        {"data": [], "totalPaginas": -1},
        {"data": [{}], "totalPaginas": 0},
        {"data": [], "totalPaginas": 1},
        {"data": [{}], "totalPaginas": 1, "numeroPagina": 2},
    ],
)
def test_envelope_malformado_rejeitado(resp):
    with pytest.raises(ValueError):
        _validar_pagina(resp)
