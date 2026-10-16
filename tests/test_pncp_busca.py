"""Busca PNCP (R3): mapeamento, contrato, carga atômica e dedupe com o ARP na view."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import httpx
import pytest

from pncp_ti.fontes import pncp_busca as b
from pncp_ti.fontes.siga_csv import ErroValidacao

HOJE = date(2026, 10, 16)
ID_A = "00394502000144-1-009124/2026-000001"
ID_B = "11111111000191-1-000010/2026-000002"


def item(id_ata: str = ID_A, **extra) -> dict:
    base = {
        "numero_controle_pncp": id_ata,
        "title": "Ata nº 02076/2026",
        "description": "Aquisição de Notebook / Desktop",
        "item_url": "/atas/00394502000144/2026/9124/1",
        "orgao_nome": "COMANDO DA MARINHA",
        "unidade_nome": "BATALHÃO NAVAL",
        "esfera_nome": "Federal",
        "uf": "RJ",
        "municipio_nome": "Rio de Janeiro",
        "situacao_nome": "Divulgada no PNCP",
        "data_inicio_vigencia": "2026-09-02",
        "data_fim_vigencia": "2027-09-02",
        "data_atualizacao_pncp": "2026-09-01T12:32:51",
        "cancelado": False,
        "valor_global": None,
    }
    return {**base, **extra}


def cliente(respostas: dict[str, list[dict]], chamadas: list | None = None) -> httpx.AsyncClient:
    def tratar(req: httpx.Request) -> httpx.Response:
        termo = req.url.params["q"]
        pagina = int(req.url.params["pagina"])
        tam = int(req.url.params["tam_pagina"])
        todos = respostas.get(termo, [])
        if chamadas is not None:
            chamadas.append(dict(req.url.params))
        return httpx.Response(
            200, json={"items": todos[(pagina - 1) * tam : pagina * tam], "total": len(todos)}
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(tratar))


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(b, "REQUISICOES_POR_SEGUNDO", 1000.0)
    monkeypatch.setattr(b, "ESPERA_BASE", 0.0)


def test_mapear_aceita_ata_vigente_e_monta_link():
    ata = b.mapear(item(), "notebook", HOJE)
    assert ata is not None
    assert ata.id_origem == ID_A
    assert ata.link_origem == "https://pncp.gov.br/app/atas/00394502000144/2026/9124/1"
    assert ata.esfera == "Federal" and ata.uf == "RJ"
    assert ata.vigente_na_origem
    assert ata.motivo_ti == "termo_pncp:notebook"


@pytest.mark.parametrize(
    "extra",
    [
        {"data_fim_vigencia": "2026-10-15"},  # vencida
        {"data_fim_vigencia": None},
        {"numero_controle_pncp": "sem-formato"},
        {"item_url": "/contratos/1"},
        {"description": "  "},
    ],
)
def test_mapear_descarta_o_que_nao_e_ata_vigente_identificavel(extra):
    assert b.mapear(item(**extra), "notebook", HOJE) is None


def test_mapear_mascara_cpf_do_texto_e_marca_cancelada():
    ata = b.mapear(item(description="Serviço de TI 123.456.789-09", cancelado=True), "ti", HOJE)
    assert ata is not None
    assert "123.456.789-09" not in ata.objeto
    assert not ata.vigente_na_origem


@pytest.mark.parametrize(
    "corpo",
    [[], {"items": {}, "total": 1}, {"items": [], "total": "1"}, {"items": [{"x": 1}], "total": 1}],
)
def test_contrato_alterado_falha_alto(corpo):
    with pytest.raises(ErroValidacao) as exc:
        b.validar_pagina(corpo)
    assert exc.value.tipo == "contrato"


def test_ler_termos_ignora_comentarios_e_repetidos(tmp_path):
    arquivo = tmp_path / "t.txt"
    arquivo.write_text("# x\nnotebook\n\n  notebook \nsoftware  livre\n", encoding="utf-8")
    assert b.ler_termos(arquivo) == ["notebook", "software livre"]
    arquivo.write_text("# só comentário\n", encoding="utf-8")
    with pytest.raises(ErroValidacao):
        b.ler_termos(arquivo)


async def test_coletar_pagina_dedupe_e_junta_termos(monkeypatch):
    monkeypatch.setattr(b, "TAMANHO_PAGINA", 2)
    chamadas: list[dict] = []
    respostas = {
        "notebook": [item(ID_A), item(ID_B), item("22222222000191-1-000001/2026-000001")],
        "desktop": [item(ID_A)],
        "vazio": [],
    }
    async with cliente(respostas, chamadas) as c:
        coleta = await b.coletar(["notebook", "desktop", "vazio"], HOJE, c)
    assert len(coleta.atas) == 3
    assert coleta.atas[ID_A].termos == {"notebook", "desktop"}
    assert coleta.contagens["termos_sem_resultado"] == 1
    assert coleta.sem_resultado == ["vazio"]
    assert [ch["pagina"] for ch in chamadas if ch["q"] == "notebook"] == ["1", "2"]
    assert all(ch["status"] == "vigente" and ch["tipos_documento"] == "ata" for ch in chamadas)


async def test_retry_em_queda_de_conexao_e_termo_falho_nao_derruba():
    tentativas = {"n": 0}

    def tratar(req: httpx.Request) -> httpx.Response:
        if req.url.params["q"] == "ruim":
            raise httpx.ConnectError("queda")
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            return httpx.Response(200, content=b"")  # corpo vazio intermitente do portal
        return httpx.Response(200, json={"items": [item()], "total": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        coleta = await b.coletar(["bom", "ruim", "bom2", "bom3", "bom4", "bom5"], HOJE, c)
    assert coleta.contagens["termos_falhos"] == 1
    assert len(coleta.atas) == 1
    b.validar(coleta)  # 1 de 6 falhos fica abaixo do limite


async def test_validar_recusa_muitos_termos_falhos_e_coleta_vazia():
    def cair(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("queda")

    async with httpx.AsyncClient(transport=httpx.MockTransport(cair)) as c:
        coleta = await b.coletar(["a", "b"], HOJE, c)
    with pytest.raises(ErroValidacao) as exc:
        b.validar(coleta)
    assert exc.value.tipo == "termos_falhos"
    vazia = b.Coleta({}, {"termos": 1, "termos_falhos": 0}, [])
    with pytest.raises(ErroValidacao) as exc:
        b.validar(vazia)
    assert exc.value.tipo == "sem_atas"


async def test_contrato_quebrado_em_pagina_derruba_a_coleta():
    def tratar(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"resultados": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        with pytest.raises(ErroValidacao) as exc:
            await b.coletar(["notebook"], HOJE, c)
    assert exc.value.tipo == "contrato"


async def _carregar(conn, ids: list[str], hoje: date = HOJE) -> b.ResultadoCarga:
    async with cliente({"notebook": [item(i) for i in ids]}) as c:
        coleta = await b.coletar(["notebook"], hoje, c)
    return await b.publicar(conn, coleta, b._geracao(coleta, ["notebook"]), uuid4(), hoje)


async def test_publicar_e_idempotente_e_troca_a_carga(conn_ingest):
    primeira = await _carregar(conn_ingest, [ID_A, ID_B])
    segunda = await _carregar(conn_ingest, [ID_A, ID_B])
    assert primeira.carga_id != segunda.carga_id
    ativas = await (
        await conn_ingest.execute(
            "SELECT count(*) AS n FROM cargas WHERE fonte = 'pncp_busca' AND ativa"
        )
    ).fetchone()
    assert ativas["n"] == 1
    atas = await (await conn_ingest.execute("SELECT count(*) AS n FROM atas")).fetchone()
    assert atas["n"] == 2  # a carga anterior saiu junto
    vistas = await (await conn_ingest.execute("SELECT count(*) AS n FROM atas_vistas")).fetchone()
    assert vistas["n"] == 2


async def test_queda_de_volume_nao_publica(conn_ingest):
    await _carregar(conn_ingest, [ID_A, ID_B, "33333333000191-1-000001/2026-000001"])
    with pytest.raises(ErroValidacao) as exc:
        await _carregar(conn_ingest, [ID_A])
    assert exc.value.tipo == "queda_volume"
    await conn_ingest.rollback()
    ativa = await (
        await conn_ingest.execute(
            "SELECT contagens FROM cargas WHERE fonte = 'pncp_busca' AND ativa"
        )
    ).fetchone()
    assert ativa["contagens"]["atas_unicas"] == 3


async def test_view_prefere_o_arp_na_mesma_ata_e_mantem_a_busca_no_resto(conn_ingest, conn_reader):
    await _carregar(conn_ingest, [ID_A, ID_B])
    carga = uuid4()
    await conn_ingest.execute(
        "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
        "VALUES (%s, 'compras_arp', %s, 'concluida', true)",
        (carga, HOJE),
    )
    await conn_ingest.execute(
        "INSERT INTO atas (carga_id, id_origem, numero, objeto, status_origem, is_ti, "
        "vigente_na_origem, numero_controle_pncp, fim) "
        "VALUES (%s, %s, '1', 'notebooks', 'Ativa', true, true, %s, %s)",
        (carga, ID_A, ID_A, date.today() + timedelta(days=30)),
    )
    await conn_ingest.commit()
    linhas = await (
        await conn_reader.execute(
            "SELECT id_ata, fonte, esfera, uf FROM v_atas_ti_vigentes ORDER BY fonte, id_ata"
        )
    ).fetchall()
    assert [(r["fonte"], r["id_ata"]) for r in linhas] == [
        ("compras_arp", ID_A),
        ("pncp_busca", ID_B),
    ]
    busca = next(r for r in linhas if r["fonte"] == "pncp_busca")
    assert (busca["esfera"], busca["uf"]) == ("Federal", "RJ")
