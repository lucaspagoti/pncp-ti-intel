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
    monkeypatch.setattr(b, "ESPERA_PASSADA", 0.0)


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
        termo = req.url.params["q"]
        corpo = {"items": [item(description=f"Aquisição de {termo}")], "total": 1}
        return httpx.Response(200, json=corpo)

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        coleta = await b.coletar(["bom", "ruim", "bom2", "bom3", "bom4", "bom5"], HOJE, c)
    assert coleta.contagens["termos_falhos"] == 1
    assert coleta.falhos == ["ruim"]
    assert len(coleta.atas) == 1
    b.validar(coleta)  # o termo perdido é decidido na publicação (ADR 0028)


async def test_validar_recusa_coleta_vazia_mesmo_com_todos_os_termos_falhos():
    def cair(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("queda")

    async with httpx.AsyncClient(transport=httpx.MockTransport(cair)) as c:
        coleta = await b.coletar(["a", "b"], HOJE, c)
    with pytest.raises(ErroValidacao) as exc:
        b.validar(coleta)
    assert exc.value.tipo == "sem_atas"
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


@pytest.mark.parametrize(
    ("objeto", "termo", "esperado"),
    [
        ("Aquisição de Notebooks para a escola", "notebook", True),
        ("EQUIPAMENTOS DE INFORMÁTICA E PERIFÉRICOS", "equipamentos de informatica", True),
        (
            "Aquisição de equipamentos de escritório e informática",
            "equipamentos de informatica",
            False,
        ),
        ("Mobiliário e equipamentos diversos", "equipamentos de informatica", False),
        ("Licença de uso de software", "licenca de software", False),
        ("Contratação de nuvem pública", "nuvem", True),
        ("Anuvem", "nuvem", False),  # início de palavra, não meio
        ("qualquer coisa", "   ", False),
    ],
)
def test_casa_termo_exige_a_frase_inteira(objeto, termo, esperado):
    assert b.casa_termo(objeto, termo) is esperado


async def test_coletar_descarta_o_que_o_portal_devolve_por_palavra_solta():
    respostas = {
        "equipamentos de informatica": [
            item(ID_A, description="EQUIPAMENTOS DE INFORMÁTICA E PERIFÉRICOS"),
            item(ID_B, description="Mobiliário e equipamentos diversos"),
        ]
    }
    async with cliente(respostas) as c:
        coleta = await b.coletar(["equipamentos de informatica"], HOJE, c)
    assert list(coleta.atas) == [ID_A]
    assert coleta.contagens["itens_sem_termo"] == 1


async def test_termo_que_falha_ganha_segunda_chance():
    chamadas = {"n": 0}

    def tratar(req: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] <= b.TENTATIVAS:  # esgota as tentativas do 1º termo, depois volta
            raise httpx.ReadError("queda")
        return httpx.Response(200, json={"items": [item()], "total": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        coleta = await b.coletar(["notebook"], HOJE, c)
    assert coleta.contagens["termos_falhos"] == 0
    assert coleta.contagens["termos_recuperados"] == 1
    assert ID_A in coleta.atas


async def test_pagina_vazia_antes_do_total_declarado_falha_o_termo():
    def tratar(req: httpx.Request) -> httpx.Response:
        pagina = int(req.url.params["pagina"])
        itens = [item()] if pagina == 1 else []
        return httpx.Response(200, json={"items": itens, "total": 3})

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        with pytest.raises(b._TermoFalhou):
            await b.buscar_termo(c, b.LimitadorTaxa(1000), "notebook")
        coleta = await b.coletar(["notebook"], HOJE, c)
    assert coleta.contagens["termos_falhos"] == 1  # incompleto não vira lista "completa"


async def test_registra_o_total_declarado_por_termo_para_o_alerta_da_operacao():
    respostas = {"notebook": [item(ID_A), item(ID_B)], "vazio": []}
    async with cliente(respostas) as c:
        coleta = await b.coletar(["notebook", "vazio"], HOJE, c)
    assert coleta.contagens["resultados_por_termo"] == {"notebook": 2, "vazio": 0}


async def test_resposta_acima_do_limite_de_bytes_derruba_a_coleta(monkeypatch):
    monkeypatch.setattr(b, "LIMITE_BYTES", 1000)

    def tratar(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000)

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        with pytest.raises(ErroValidacao) as exc:
            await b.coletar(["notebook"], HOJE, c)
    assert exc.value.tipo == "contrato"


async def test_termo_que_nunca_volta_conta_como_falho_depois_das_passadas():
    chamadas = {"n": 0}

    def tratar(req: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        raise httpx.ReadError("queda")

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        coleta = await b.coletar(["notebook"], HOJE, c)
    assert chamadas["n"] == b.TENTATIVAS * (1 + b.PASSADAS_EXTRA)
    assert coleta.contagens["termos_falhos"] == 1


async def test_pagina_vazia_com_total_zerado_no_meio_nao_vira_fim_de_lista():
    def tratar(req: httpx.Request) -> httpx.Response:
        if int(req.url.params["pagina"]) == 1:
            return httpx.Response(200, json={"items": [item()], "total": 3})
        return httpx.Response(200, json={"items": [], "total": 0})  # o portal "zerou" no meio

    async with httpx.AsyncClient(transport=httpx.MockTransport(tratar)) as c:
        with pytest.raises(b._TermoFalhou):
            await b.buscar_termo(c, b.LimitadorTaxa(1000), "notebook")


def _ata(id_ata: str, objeto: str, fim: date = date(2027, 1, 1), termo: str = "x") -> b.AtaBusca:
    ata = b.mapear(item(id_ata, description=objeto), termo, HOJE)
    assert ata is not None
    ata.fim = fim
    return ata


def _coleta(atas: list[b.AtaBusca], falhos: list[str]) -> b.Coleta:
    contagens = {"termos": 3, "termos_falhos": len(falhos), "atas_unicas": len(atas)}
    return b.Coleta({a.id_origem: a for a in atas}, contagens, [], falhos)


ID_C = "33333333000191-1-000001/2026-000001"
ID_D = "44444444000191-1-000001/2026-000001"


def test_termo_falho_reaproveita_as_atas_da_carga_ativa_que_casam_o_termo():
    nova = _ata(ID_A, "Aquisição de equipamentos de informática e notebook", termo="notebook")
    coleta = _coleta([nova], ["equipamentos de informatica"])
    anteriores = {
        ID_A: _ata(ID_A, "Aquisição de equipamentos de informática e notebook"),
        ID_B: _ata(ID_B, "Registro de preços de EQUIPAMENTOS DE INFORMÁTICA"),
        ID_C: _ata(ID_C, "Equipamentos de informática", fim=HOJE - timedelta(days=1)),
        ID_D: _ata(ID_D, "Mobiliário de escritório"),
    }
    b.reaproveitar(coleta, anteriores, {}, HOJE)
    assert set(coleta.atas) == {ID_A, ID_B}  # vencida e a que não casa ficam fora
    assert coleta.atas[ID_A].termos == {"notebook", "equipamentos de informatica"}
    assert coleta.atas[ID_B].termos == {"equipamentos de informatica"}
    c = coleta.contagens
    assert c["termos_pendentes"] == {"equipamentos de informatica": HOJE.isoformat()}
    assert c["termos_reaproveitados"] == ["equipamentos de informatica"]
    assert c["atas_reaproveitadas"] == 1
    assert c["atas_unicas"] == 2


def test_termo_sem_base_anterior_publica_vazio_e_fica_pendente():
    coleta = _coleta([_ata(ID_A, "notebook", termo="notebook")], ["material de informatica"])
    b.reaproveitar(coleta, {}, {}, HOJE)
    assert set(coleta.atas) == {ID_A}
    assert coleta.contagens["termos_pendentes"] == {"material de informatica": HOJE.isoformat()}
    assert coleta.contagens["termos_reaproveitados"] == []
    assert coleta.contagens["atas_reaproveitadas"] == 0


def test_pendencia_herdada_mantem_a_data_e_falha_ao_passar_do_limite():
    ainda = (HOJE - timedelta(days=b.DIAS_PENDENTE - 1)).isoformat()
    coleta = _coleta([_ata(ID_A, "notebook", termo="notebook")], ["software"])
    b.reaproveitar(coleta, {}, {"software": ainda}, HOJE)
    assert coleta.contagens["termos_pendentes"] == {"software": ainda}

    passou = (HOJE - timedelta(days=b.DIAS_PENDENTE)).isoformat()
    coleta = _coleta([_ata(ID_A, "notebook", termo="notebook")], ["software"])
    with pytest.raises(ErroValidacao) as exc:
        b.reaproveitar(coleta, {}, {"software": passou}, HOJE)
    assert exc.value.tipo == "termos_falhos"
    assert "software" in str(exc.value)


def test_termo_que_volta_a_responder_limpa_a_pendencia():
    coleta = _coleta([_ata(ID_A, "notebook", termo="notebook")], [])
    b.reaproveitar(coleta, {}, {"notebook": (HOJE - timedelta(days=1)).isoformat()}, HOJE)
    assert coleta.contagens["termos_pendentes"] == {}
    assert coleta.contagens["termos_reaproveitados"] == []


async def test_publicar_com_termo_falho_reaproveita_a_carga_ativa(conn_ingest):
    def respostas(falhar: bool):
        def tratar(req: httpx.Request) -> httpx.Response:
            termo = req.url.params["q"]
            if termo == "desktop" and falhar:
                raise httpx.ReadError("queda")
            ids = [ID_A, ID_B] if termo == "notebook" or not falhar else [ID_B]
            ids = [ID_A] if termo == "desktop" else ids
            return httpx.Response(200, json={"items": [item(i) for i in ids], "total": len(ids)})

        return httpx.AsyncClient(transport=httpx.MockTransport(tratar))

    termos = ["notebook", "desktop"]
    async with respostas(False) as c:
        coleta = await b.coletar(termos, HOJE, c)
    await b.publicar(conn_ingest, coleta, b._geracao(coleta, termos), uuid4(), HOJE)

    async with respostas(True) as c:  # notebook só devolve B; desktop cai
        coleta = await b.coletar(termos, HOJE, c)
    coleta.atas.pop(ID_A, None)  # A só existia na carga ativa por "desktop"
    resultado = await b.publicar(conn_ingest, coleta, b._geracao(coleta, termos), uuid4(), HOJE)

    assert resultado.status == "concluida"
    assert resultado.contagens["termos_pendentes"] == {"desktop": HOJE.isoformat()}
    assert resultado.contagens["atas_reaproveitadas"] == 1
    assert "desktop" not in resultado.contagens["resultados_por_termo"]
    linhas = await (
        await conn_ingest.execute(
            "SELECT id_origem, motivo_ti FROM atas WHERE carga_id = %s ORDER BY id_origem",
            (resultado.carga_id,),
        )
    ).fetchall()
    assert {r["id_origem"]: r["motivo_ti"] for r in linhas} == {
        ID_A: "termo_pncp:desktop",
        ID_B: "termo_pncp:desktop|notebook",  # o objeto de B também casa "desktop"
    }
