"""Coletor de atas pela API oficial do PNCP (R3.1, ADR 0038): parse, delta, semente e carga."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import httpx
import pytest
from compras_mcp.clients.pncp import PNCPClient

from pncp_ti.fontes import pncp_atas as pa
from pncp_ti.fontes import pncp_busca as b
from pncp_ti.fontes.siga_csv import ErroValidacao

HOJE = date(2026, 11, 10)  # terça
ID_A = "00394502000144-1-009124/2026-000001"
ID_B = "11111111000191-1-000010/2026-000002"
ID_C = "22222222000191-1-000020/2025-000003"
TERMOS = ["notebook", "equipamentos de informatica", "impressora"]
PADS = pa.padroes(TERMOS)


def item(id_ata: str = ID_A, **extra) -> dict:
    base = {
        "numeroControlePNCPAta": id_ata,
        "numeroAtaRegistroPreco": "042",
        "anoAta": 2026,
        "objetoContratacao": "Registro de preços para aquisição de notebooks",
        "vigenciaInicio": "2026-09-02",
        "vigenciaFim": "2027-09-02",
        "cancelado": False,
        "dataAtualizacaoGlobal": "2026-11-09T10:00:00",
        "nomeOrgao": "MUNICÍPIO DE EXEMPLO",
        "nomeUnidadeOrgao": "SECRETARIA DE ADMINISTRAÇÃO",
        "codigoUnidadeOrgao": "123456",
        "cnpjOrgao": id_ata[:14],
    }
    return {**base, **extra}


def envelope(itens: list[dict], total: int | None = None, paginas: int = 1) -> dict:
    total = len(itens) if total is None else total
    return {
        "data": itens,
        "totalRegistros": total,
        "totalPaginas": paginas,
        "numeroPagina": 1,
        "paginasRestantes": 0,
        "empty": not itens,
    }


def ata(id_ata: str, objeto: str, **extra) -> b.AtaBusca:
    campos = dict(
        id_origem=id_ata,
        numero="Ata nº 1/2026",
        unidade_gerenciadora="U",
        orgao="O",
        objeto=objeto,
        inicio=HOJE - timedelta(days=30),
        fim=HOJE + timedelta(days=300),
        status_origem="Suspensa",
        cancelada=False,
        link_origem=pa.link(id_ata),
        valor_total=None,
        esfera="Municipal",
        uf="RJ",
        municipio="Niterói",
        atualizado_em="2026-10-01",
    )
    campos.update(extra)
    return b.AtaBusca(**campos)


class cliente:  # noqa: N801 - usado como `async with cliente(...) as c`
    """PNCPClient com transporte falso. O `__aenter__` dele criaria um cliente de rede real."""

    def __init__(self, tratar):
        self.c = PNCPClient(base_url=pa.URL_CONSULTA, max_retries=0)
        self.c._client = httpx.AsyncClient(
            base_url=pa.URL_CONSULTA, transport=httpx.MockTransport(tratar)
        )

    async def __aenter__(self) -> PNCPClient:
        return self.c

    async def __aexit__(self, *_):
        await self.c._client.aclose()


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(pa, "REQUISICOES_POR_SEGUNDO", 1000.0)
    monkeypatch.setattr(pa, "ESPERA_BASE", 0.0)


def test_link_do_portal_a_partir_do_id_da_ata():
    assert pa.link(ID_A) == "https://pncp.gov.br/app/atas/00394502000144/2026/9124/1"
    assert pa.link("lixo") is None


def test_mapear_ata_de_ti_vigente():
    a = pa.mapear(item(), PADS, HOJE)
    assert isinstance(a, b.AtaBusca)
    assert a.termos == {"notebook"}
    assert a.motivo_ti == "termo_pncp:notebook"
    assert a.numero == "Ata nº 042/2026"
    assert a.orgao == "MUNICÍPIO DE EXEMPLO"
    assert a.fim == date(2027, 9, 2)
    assert a.link_origem.endswith("/atas/00394502000144/2026/9124/1")
    assert a.status_origem == "Divulgada no PNCP"


@pytest.mark.parametrize(
    "extra",
    [
        {"cancelado": True},
        {"vigenciaFim": "2026-11-09"},
        {"objetoContratacao": "Aquisição de mobiliário de escritório"},
        {"objetoContratacao": "Equipamentos diversos de informática"},  # frase inteira, não palavra
    ],
)
def test_mapear_tira_da_base_o_que_nao_e_ti_vigente(extra):
    assert pa.mapear(item(**extra), PADS, HOJE) is None


@pytest.mark.parametrize(
    "extra",
    [{"numeroControlePNCPAta": "x"}, {"vigenciaFim": None}, {"objetoContratacao": ""}],
)
def test_mapear_ilegivel_nao_mexe_na_base(extra):
    assert pa.mapear(item(**extra), PADS, HOJE) is False


def test_varias_versoes_da_mesma_ata_vale_a_mais_nova():
    itens = [
        item(ID_A, cancelado=True, dataAtualizacaoGlobal="2026-11-09T12:00:00"),
        item(ID_A, dataAtualizacaoGlobal="2026-11-08T12:00:00"),
        item(ID_B, dataAtualizacaoGlobal="2026-11-08T12:00:00"),
        item(ID_B, objetoContratacao="Impressora laser", dataAtualizacaoGlobal="2026-11-09T09:00"),
    ]
    d = pa.ler_delta(itens, PADS, HOJE)
    assert d.saem == {ID_A}
    assert set(d.entram) == {ID_B}
    assert d.entram[ID_B].termos == {"impressora"}
    assert d.unidades == {ID_B: "123456"}


def test_delta_aplica_entradas_e_saidas_sobre_a_carga_ativa():
    base = {
        ID_A: ata(ID_A, "Aquisição de notebooks"),
        ID_B: ata(ID_B, "Aquisição de equipamentos de informática"),
        ID_C: ata(ID_C, "Locação de impressoras", fim=HOJE - timedelta(days=1)),
    }
    itens = [
        item(ID_A, objetoContratacao="Aquisição de notebooks e impressoras"),
        item(ID_B, cancelado=True),
    ]
    d = pa.ler_delta(itens, PADS, HOJE)
    atas, c = pa.aplicar(base, d, PADS, HOJE)
    assert set(atas) == {ID_A}  # B cancelada, C vencida
    assert atas[ID_A].termos == {"notebook", "impressora"}
    # A ata atualizada preserva o que a consulta não traz: cadastro da unidade e status.
    assert (atas[ID_A].uf, atas[ID_A].municipio, atas[ID_A].status_origem) == (
        "RJ",
        "Niterói",
        "Suspensa",
    )
    assert c["atas_removidas"] == 1 and c["atas_novas"] == 0


def test_delta_recalcula_os_termos_da_base_pela_lista_atual():
    base = {ID_A: ata(ID_A, "Aquisição de notebooks"), ID_B: ata(ID_B, "Aquisição de tablets")}
    atas, _ = pa.aplicar(base, pa.Delta(), PADS, HOJE)
    assert set(atas) == {ID_A}  # "tablet" não está na lista de teste
    assert atas[ID_A].termos == {"notebook"}


def test_ata_que_a_api_nao_mostrou_continua_na_base():
    """A semente é aditiva: ata pulada pela paginação (a lista muda em horas) não some."""
    base = {ID_A: ata(ID_A, "Aquisição de notebooks"), ID_B: ata(ID_B, "Aquisição de notebooks")}
    atas, c = pa.aplicar(base, pa.ler_delta([item(ID_A)], PADS, HOJE), PADS, HOJE)
    assert set(atas) == {ID_A, ID_B}
    assert atas[ID_A].uf == "RJ"  # empresta o cadastro da unidade
    assert c["atas_novas"] == 0


def test_versao_mais_velha_que_a_da_base_e_ignorada():
    """Um delta publicado durante a semente não é desfeito pelo que ela leu horas antes."""
    base = {
        ID_A: ata(ID_A, "Aquisição de notebooks", atualizado_em="2026-11-10T08:00:00.1"),
        ID_B: ata(ID_B, "Aquisição de notebooks", atualizado_em="2026-11-10T08:00:00.1"),
    }
    itens = [
        item(ID_A, objetoContratacao="Notebook e impressora", dataAtualizacaoGlobal="2026-11-09"),
        item(ID_B, cancelado=True, dataAtualizacaoGlobal="2026-11-09"),
        item(ID_C, dataAtualizacaoGlobal="2026-11-09"),
    ]
    atas, c = pa.aplicar(base, pa.ler_delta(itens, PADS, HOJE), PADS, HOJE)
    assert set(atas) == {ID_A, ID_B, ID_C}
    assert atas[ID_A].termos == {"notebook"}
    assert c["atas_versao_antiga"] == 2 and c["atas_novas"] == 1
    # Mesma data: a API vale (a busca dá a hora, a API só o dia).
    itens = [item(ID_B, cancelado=True, dataAtualizacaoGlobal="2026-11-10")]
    atas, c = pa.aplicar(base, pa.ler_delta(itens, PADS, HOJE), PADS, HOJE)
    assert ID_B not in atas and c["atas_removidas"] == 1


def test_ata_com_vigencia_futura_entra():
    ata_ = pa.mapear(item(vigenciaInicio="2026-11-20", vigenciaFim="2027-11-20"), PADS, HOJE)
    assert isinstance(ata_, b.AtaBusca)


@pytest.mark.parametrize(
    "marca,motivo,inicial,truncada",
    [
        (None, "sem_marca_dagua", "20261102", False),
        ("lixo", "marca_dagua_invalida", "20261102", False),
        ("2026-11-11", "marca_dagua_futura", "20261102", False),
        ("2026-10-01", "marca_dagua_velha", "20261010", True),
        ("2026-11-09", "delta", "20261108", False),
    ],
)
def test_planejar_o_delta(marca, motivo, inicial, truncada):
    p = pa.planejar(marca, HOJE)
    assert (p.motivo, p.janela_truncada) == (motivo, truncada)
    assert p.filtros == {"dataInicial": inicial, "dataFinal": "20261110"}


def test_semente_pega_a_vigencia_que_comeca_em_ate_um_ano():
    # A API recusa período maior que 365 dias.
    assert pa.filtros_semente(HOJE) == {"dataInicial": "20261110", "dataFinal": "20271109"}


@pytest.mark.parametrize(
    "corpo",
    [
        [],
        {"data": None, "totalRegistros": 0, "totalPaginas": 0},
        {"data": [], "totalRegistros": "1", "totalPaginas": 1},
        {"data": [], "totalRegistros": 1},
        {"data": [{"numeroControlePNCPAta": ID_A}], "totalRegistros": 1, "totalPaginas": 1},
    ],
)
def test_contrato_alterado_falha_alto(corpo):
    with pytest.raises(ErroValidacao) as exc:
        pa.validar_pagina(corpo)
    assert exc.value.tipo == "contrato"


async def test_pagina_tudo_e_manda_os_filtros():
    chamadas = []
    paginas = {1: [item(ID_A)], 2: [item(ID_B)]}

    def tratar(req: httpx.Request) -> httpx.Response:
        chamadas.append(dict(req.url.params))
        n = int(req.url.params["pagina"])
        return httpx.Response(200, json=envelope(paginas[n], total=2, paginas=2))

    async with cliente(tratar) as c:
        itens, total = await pa.paginar(
            c, pa.LimitadorTaxa(1000), pa.ROTA_DELTA, {"dataInicial": "20261108"}, b.Telemetria()
        )
    assert [i["numeroControlePNCPAta"] for i in itens] == [ID_A, ID_B]
    assert total == 2
    assert [ch["pagina"] for ch in chamadas] == ["1", "2"]
    assert all(ch["tamanhoPagina"] == "500" and ch["dataInicial"] == "20261108" for ch in chamadas)


async def test_janela_sem_registros_204_e_lista_vazia():
    async with cliente(lambda req: httpx.Response(204)) as c:
        itens, total = await pa.paginar(
            c, pa.LimitadorTaxa(1000), pa.ROTA_DELTA, {}, b.Telemetria()
        )
    assert (itens, total) == ([], 0)


async def test_204_no_meio_da_paginacao_falha():
    def tratar(req: httpx.Request) -> httpx.Response:
        if req.url.params["pagina"] == "2":
            return httpx.Response(204)
        return httpx.Response(200, json=envelope([item()], total=2, paginas=2))

    async with cliente(tratar) as c:
        with pytest.raises(ErroValidacao) as exc:
            await pa.paginar(c, pa.LimitadorTaxa(1000), pa.ROTA_DELTA, {}, b.Telemetria())
    assert exc.value.tipo == "pagina_vazia"


async def test_429_queda_e_5xx_tentam_de_novo_e_contam_na_telemetria(monkeypatch):
    esperas = []

    async def dormir(s):
        if s >= 0.1:
            esperas.append(s)

    monkeypatch.setattr(pa.asyncio, "sleep", dormir)
    monkeypatch.setattr(pa, "ESPERA_BASE", 5.0)
    respostas = iter(["429", "reset", "503", "ok"])

    def tratar(req: httpx.Request) -> httpx.Response:
        r = next(respostas)
        if r == "reset":
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        if r == "ok":
            return httpx.Response(200, json=envelope([item()]))
        return httpx.Response(int(r), headers={"Retry-After": "0"})

    t = b.Telemetria()
    async with cliente(tratar) as c:
        itens, _ = await pa.paginar(c, pa.LimitadorTaxa(1000), pa.ROTA_DELTA, {}, t)
    assert len(itens) == 1
    assert esperas == [5.0, 10.0, 20.0]
    assert t.contagens()["falhas_por_tipo"] == {"http_429": 1, "http_5xx": 1, "reset": 1}


async def test_esgota_as_tentativas_e_falha_como_rede(monkeypatch):
    def tratar(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with cliente(tratar) as c:
        with pytest.raises(ErroValidacao) as exc:
            await pa.paginar(c, pa.LimitadorTaxa(1000), pa.ROTA_DELTA, {}, b.Telemetria())
    assert exc.value.tipo == "rede"
    assert b.codigo_saida(exc.value) == 1  # instável: o script tenta a busca do portal


async def test_4xx_e_mudanca_de_contrato(monkeypatch):
    async with cliente(lambda req: httpx.Response(400, text="Tamanho de página inválido")) as c:
        with pytest.raises(ErroValidacao) as exc:
            await pa.paginar(c, pa.LimitadorTaxa(1000), pa.ROTA_DELTA, {}, b.Telemetria())
    assert exc.value.tipo == "contrato"
    assert b.codigo_saida(exc.value) == 2


def test_resultados_por_termo_alimenta_o_gancho_da_operacao():
    atas = {ID_A: ata(ID_A, "x", termos={"notebook"}), ID_B: ata(ID_B, "y", termos={"notebook"})}
    assert pa.resultados_por_termo(atas, TERMOS) == {
        "notebook": 2,
        "equipamentos de informatica": 0,
        "impressora": 0,
    }


def test_checkpoint_retoma_da_pagina_seguinte(tmp_path):
    ck = pa.Checkpoint(tmp_path / "semente.jsonl")
    filtros = pa.filtros_semente(HOJE)
    assert ck.abrir(filtros, TERMOS, HOJE)[2:] == (1, 0, 0, 0)
    ck.gravar(pa.Pagina(1, 3, 1500, [item(ID_A), item(ID_B)]), [item(ID_A)])
    ck.gravar(pa.Pagina(2, 3, 1500, [item(ID_C)]), [])
    with ck.caminho.open("a") as f:
        f.write('{"pagina": 3, "lid')  # queda no meio da gravação
    # No dia seguinte retoma com a janela do início, e a linha cortada é descartada.
    cab, itens, proxima, total, lidos, declarado = ck.abrir(
        pa.filtros_semente(HOJE + timedelta(days=1)), TERMOS, HOJE + timedelta(days=1)
    )
    assert cab["filtros"] == filtros
    assert [i["numeroControlePNCPAta"] for i in itens] == [ID_A]
    assert (proxima, total, lidos, declarado) == (3, 3, 3, 1500)
    assert len(ck.caminho.read_text().splitlines()) == 3


@pytest.mark.parametrize("termos,dias", [(TERMOS, 4), (["notebook"], 0)])
def test_checkpoint_velho_ou_de_outros_termos_recomeca(tmp_path, termos, dias):
    ck = pa.Checkpoint(tmp_path / "semente.jsonl")
    ck.abrir(pa.filtros_semente(HOJE), TERMOS, HOJE)
    ck.gravar(pa.Pagina(1, 2, 600, [item()]), [item()])
    dia = HOJE + timedelta(days=dias)
    cab, itens, proxima, *_ = ck.abrir(pa.filtros_semente(dia), termos, dia)
    assert (itens, proxima, cab["inicio"]) == ([], 1, dia.isoformat())


async def _publicar(conn, coleta, dia):
    return await b.publicar(conn, coleta, b._geracao(coleta, TERMOS), uuid4(), dia)


async def test_semente_retoma_e_delta_continua_da_marca(conn_ingest, tmp_path, monkeypatch):
    """Ponta a ponta no banco: semente que cai e retoma, delta, reserva e delta de novo."""
    monkeypatch.setattr(pa, "RETOMADAS", 0)
    ck = pa.Checkpoint(tmp_path / "semente.jsonl")
    paginas_vistas = []
    cair = {"sim": True}

    def tratar(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/atualizacao"):
            delta = [item(ID_B, cancelado=True), item(ID_C, objetoContratacao="Notebook")]
            return httpx.Response(200, json=envelope(delta))
        n = int(req.url.params["pagina"])
        paginas_vistas.append(n)
        if n == 2 and cair["sim"]:
            return httpx.Response(503)
        lista = [item(ID_A)] if n == 1 else [item(ID_B, objetoContratacao="Impressoras")]
        return httpx.Response(200, json=envelope(lista, total=2, paginas=2))

    async with cliente(tratar) as c:
        with pytest.raises(ErroValidacao):
            await pa.coletar_semente(conn_ingest, c, TERMOS, HOJE, ck)
    cair["sim"] = False
    paginas_vistas.clear()
    async with cliente(tratar) as c:
        coleta, _ = await pa.coletar_semente(conn_ingest, c, TERMOS, HOJE, ck)
    assert set(paginas_vistas) == {2}  # retomou: a página 1 veio do checkpoint
    assert coleta.contagens["modo"] == "semente"
    assert coleta.contagens["registros_lidos"] == 2
    assert set(coleta.atas) == {ID_A, ID_B}
    r1 = await _publicar(conn_ingest, coleta, HOJE)
    assert r1.contagens["marca_dagua"] == HOJE.isoformat()  # sem marca anterior: o início

    amanha = HOJE + timedelta(days=1)
    async with cliente(tratar) as c:
        coleta, _ = await pa.coletar(conn_ingest, c, TERMOS, amanha)
    assert coleta.contagens["janela"] == {"dataInicial": "20261109", "dataFinal": "20261111"}
    r2 = await _publicar(conn_ingest, coleta, amanha)
    linhas = await (
        await conn_ingest.execute(
            "SELECT id_origem, motivo_ti FROM atas WHERE carga_id = %s", (r2.carga_id,)
        )
    ).fetchall()
    assert {r["id_origem"]: r["motivo_ti"] for r in linhas} == {
        ID_A: "termo_pncp:notebook",
        ID_C: "termo_pncp:notebook",
    }
    assert r2.contagens["atas_removidas"] == 1

    # A reserva (busca do portal) publica sem marca d'água; o delta segue da última da API.
    depois = amanha + timedelta(days=1)
    reserva = b.Coleta(dict(coleta.atas), {"atas_unicas": 2}, sem_resultado=[], falhos=[])
    await _publicar(conn_ingest, reserva, depois)
    async with cliente(tratar) as c:
        coleta, _ = await pa.coletar(conn_ingest, c, TERMOS, depois + timedelta(days=1))
    assert coleta.contagens["motivo_modo"] == "delta"
    assert coleta.contagens["janela"]["dataInicial"] == "20261110"
