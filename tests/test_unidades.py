"""Esfera, UF e município do ARP pelo cadastro de unidades do PNCP (ADR 0034).

Fixtures recortadas de respostas reais de 02/11/2026 (dados públicos de órgãos).
"""

from __future__ import annotations

import json

import arp_dados as d
import httpx
import pytest
from test_arp_carga import CONFIG

from pncp_ti.fontes import arp, unidades

UNIDADE = {
    "id": 2412664,
    "orgao": {
        "id": 13873,
        "cnpj": "14814139000183",
        "razaoSocial": "FUNDACAO ESTATAL DE ATENCAO A SAUDE - FEAS",
        "poderId": "E",
        "esferaId": "M",
        "validado": True,
    },
    "codigoUnidade": "926734",
    "nomeUnidade": "INSTITUTO DE PESQ. E PLAN. URB. DE CURITIBA",
    "municipio": {
        "id": 4006,
        "uf": {"siglaUF": "PR", "nomeUF": "Paraná"},
        "nome": "Curitiba",
        "codigoIbge": "4106902",
    },
    "statusAtivo": True,
}
ORGAO = {
    "cnpj": "14814139000183",
    "razaoSocial": "FUNDACAO ESTATAL DE ATENCAO A SAUDE - FEAS",
    "poderId": "E",
    "esferaId": "M",
    "validado": True,
}


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(unidades, "ESPERA_BASE", 0.0)
    monkeypatch.setattr(unidades, "REQUISICOES_POR_SEGUNDO", 1000.0)


def cliente(respostas: dict[str, tuple[int, object]], pedidos: list[str] | None = None):
    def tratar(request: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(request.url.path)
        status, corpo = respostas.get(request.url.path, (404, {"message": "not found"}))
        return httpx.Response(status, content=json.dumps(corpo).encode())

    return httpx.AsyncClient(transport=httpx.MockTransport(tratar))


CAMINHO_UNIDADE = "/api/pncp/v1/orgaos/14814139000183/unidades/926734"
CAMINHO_ORGAO = "/api/pncp/v1/orgaos/14814139000183"
CHAVE = ("14814139000183", "926734")


def test_contrato_da_unidade_e_do_orgao():
    assert unidades.mapear_unidade(UNIDADE) == unidades.Unidade("Municipal", "PR", "Curitiba")
    assert unidades.mapear_orgao(ORGAO) == unidades.Unidade("Municipal", None, None)
    with pytest.raises(unidades.ErroContrato):
        unidades.mapear_unidade({"orgao": {}, "municipio": {}})  # sem esferaId
    with pytest.raises(unidades.ErroContrato):
        unidades.mapear_unidade({"codigoUnidade": "1"})


def test_chave_vem_do_cnpj_no_id_da_ata():
    assert unidades.chave("14814139000183-1-000050/2026-000006", "926734") == CHAVE
    assert unidades.chave("14814139000183-1-000050/2026-000006", "") is None
    assert unidades.chave("SIGA-123", "926734") is None


async def test_unidade_sem_cadastro_cai_para_a_esfera_do_orgao():
    async with cliente({CAMINHO_ORGAO: (200, ORGAO)}) as c:
        u = await unidades.consultar(c, unidades.LimitadorTaxa(1000.0), CHAVE)
    assert u == unidades.Unidade("Municipal", None, None)


async def test_resolver_grava_cache_e_nao_reconsulta(conn_ingest):
    await conn_ingest.execute("DELETE FROM unidades_gerenciadoras")
    pedidos: list[str] = []
    async with cliente({CAMINHO_UNIDADE: (200, UNIDADE)}, pedidos) as c:
        mapa, contagens = await unidades.resolver(conn_ingest, [CHAVE], c)
        assert mapa[CHAVE].uf == "PR" and contagens["unidades_consultadas"] == 1
        mapa, contagens = await unidades.resolver(conn_ingest, [CHAVE], c)
    assert pedidos == [CAMINHO_UNIDADE]  # a segunda veio do cache
    assert mapa[CHAVE].municipio == "Curitiba" and contagens["unidades_consultadas"] == 0


async def test_falha_nao_derruba_e_cache_vencido_ainda_vale(conn_ingest):
    await conn_ingest.execute("DELETE FROM unidades_gerenciadoras")
    await conn_ingest.execute(
        "INSERT INTO unidades_gerenciadoras (cnpj, codigo, esfera, uf, municipio, consultado_em) "
        "VALUES (%s, %s, 'Municipal', 'PR', 'Curitiba', now() - interval '60 days')",
        CHAVE,
    )
    await conn_ingest.commit()
    fora = {CAMINHO_UNIDADE: (503, {}), "/api/pncp/v1/orgaos/00000000000191/unidades/1": (503, {})}
    async with cliente(fora) as c:
        mapa, contagens = await unidades.resolver(conn_ingest, [CHAVE, ("00000000000191", "1")], c)
    assert mapa[CHAVE].uf == "PR"  # vencido, mas é o melhor que há
    assert ("00000000000191", "1") not in mapa
    assert contagens["unidades_falhas"] == 2 and contagens["unidades_sem_cadastro"] == 1


async def test_carga_do_arp_grava_esfera_uf_e_municipio(conn_ingest, conn_reader):
    atas = [d.ata("1", "Aquisição de notebooks e microcomputadores")]
    itens = {d.id_ata("1"): [d.item("1", "1", "Notebook 14 pol", nome_pdm="NOTEBOOK", pdm=None)]}
    preparado, geracao = await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, itens))
    assert preparado.atas[0].codigo_unidade == "999999"
    chave = unidades.chave(preparado.atas[0].id_origem, "999999")
    mapa = {chave: unidades.Unidade("Federal", "DF", "Brasília")}
    await arp._publicar(conn_ingest, preparado, geracao, __import__("uuid").uuid4(), d.hoje(), mapa)
    cur = await conn_reader.execute("SELECT esfera, uf, municipio FROM v_atas_ti_vigentes")
    assert await cur.fetchall() == [{"esfera": "Federal", "uf": "DF", "municipio": "Brasília"}]
