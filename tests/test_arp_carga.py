"""Carga ARP no Postgres: troca atômica, idempotência, falhas, privacidade e permissões."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import arp_dados as d
import psycopg
import pytest
from compras_mcp.errors import ComprasServerError
from psycopg.errors import InsufficientPrivilege

from pncp_ti.config import get_settings
from pncp_ti.fontes import arp
from pncp_ti.fontes.siga_csv import ErroValidacao

CONFIG = replace(get_settings(), arp_requests_per_second=1000.0, arp_max_requisicoes=1000)


def _cenario():
    atas = [
        d.ata("1", "Aquisição de notebooks e microcomputadores"),  # TI pelo objeto
        d.ata("2", "Contratação de tecnologia da comunicação"),  # TI só pelo catálogo (PDM 239)
        d.ata("3", "Gêneros alimentícios"),  # não TI
        d.ata("4", "Aquisição de computadores", status="Cancelada"),  # TI, cancelada
        d.ata("5", "Aquisição de computadores", fim=d.hoje() - timedelta(days=1)),  # vencida
    ]
    itens = {
        d.id_ata("1"): [
            d.item("1", "1", "Notebook 14 pol", nome_pdm="NOTEBOOK", pdm=None),
            d.item("1", "2", "Suporte", ni=d.CPF_FICTICIO, valor=0.0),
        ],
        d.id_ata("2"): [d.item("2", "1", "Cabo de rede", pdm=239, nome_pdm="CABO")],
        d.id_ata("4"): [d.item("4", "1", "Desktop", nome_pdm="DESKTOP")],
    }
    return atas, itens


async def _carga(conn, atas=None, itens=None, **cliente):
    if atas is None:
        atas, itens = _cenario()
    cliente_falso = d.ClienteFalso(atas, itens, **cliente)
    preparado, geracao = await arp.coletar(CONFIG, d.hoje(), client=cliente_falso)
    return await arp._publicar(conn, preparado, geracao, __import__("uuid").uuid4(), d.hoje())


async def _um(conn, sql, *params):
    cur = await conn.execute(sql, params)
    return (await cur.fetchone())["n"]


async def test_carga_completa_publica_so_ti_vigente_e_classifica_com_motivo(
    conn_ingest, conn_reader
):
    resultado = await _carga(conn_ingest)
    assert resultado.status == "concluida"
    assert resultado.contagens["atas_unicas"] == 4  # a vencida fica fora da janela de listagem
    cur = await conn_reader.execute(
        "SELECT id_ata, fonte, link_origem, orgao FROM v_atas_ti_vigentes ORDER BY id_ata"
    )
    atas = await cur.fetchall()
    assert [a["id_ata"] for a in atas] == [d.id_ata("1"), d.id_ata("2")]
    assert {a["fonte"] for a in atas} == {"compras_arp"}
    assert all(a["link_origem"].startswith("https://pncp.gov.br/") for a in atas)
    cur = await conn_ingest.execute("SELECT id_origem, motivo_ti FROM atas ORDER BY id_origem")
    motivos = {r["id_origem"]: r["motivo_ti"] for r in await cur.fetchall()}
    assert motivos[d.id_ata("2")].startswith("catmat70:pdm239@item")
    assert motivos[d.id_ata("1")].endswith("@objeto")
    await conn_ingest.commit()


async def test_itens_com_preco_invalido_e_cpf_mascarado_na_view(conn_ingest, conn_reader):
    await _carga(conn_ingest)
    cur = await conn_reader.execute(
        "SELECT id_item, valor_unitario, valor_valido, id_fornecedor, maximo_adesao "
        "FROM v_ata_itens_ti WHERE id_ata = %s ORDER BY id_item",
        (d.id_ata("1"),),
    )
    itens = await cur.fetchall()
    assert [i["valor_valido"] for i in itens] == [True, False]
    assert itens[1]["valor_unitario"] is None
    assert itens[1]["id_fornecedor"].startswith("hmac:")
    assert itens[0]["maximo_adesao"] is not None
    cur = await conn_ingest.execute(
        "SELECT count(*) n FROM ata_itens WHERE descricao || fornecedor || chave || "
        "coalesce(id_fornecedor, '') LIKE %s",
        (f"%{d.CPF_FICTICIO}%",),
    )
    assert (await cur.fetchone())["n"] == 0
    await conn_ingest.commit()


async def test_executar_duas_vezes_nao_duplica_e_mantem_uma_carga_ativa(conn_ingest):
    await _carga(conn_ingest)
    await _carga(conn_ingest)
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 4
    ativas = await _um(
        conn_ingest, "SELECT count(*) n FROM cargas WHERE ativa AND fonte = %s", arp.FONTE
    )
    assert ativas == 1
    await conn_ingest.commit()


async def test_queda_de_volume_mantem_a_carga_anterior(conn_ingest):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 11)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 11)}
    await _carga(conn_ingest, atas, itens)
    with pytest.raises(ErroValidacao) as erro:
        await _carga(conn_ingest, atas[:3], {k: itens[k] for k in list(itens)[:3]})
    assert erro.value.tipo == "queda_volume"
    await conn_ingest.rollback()
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 10
    await conn_ingest.commit()


def _mesmo_dia(n: int):
    fim = d.hoje() + timedelta(days=30)
    assinatura = d.hoje() - timedelta(days=10)
    return [
        d.ata(str(k), "Gêneros alimentícios", fim=fim, assinatura=assinatura)
        for k in range(1, n + 1)
    ]


async def test_listagem_divide_janelas_e_nao_perde_atas_com_paginas_sobrepostas():
    # 40 atas em dias e assinaturas variados; páginas de 3 com sobreposição: dividir evita perda.
    atas = [
        d.ata(
            str(k),
            "Gêneros alimentícios",
            fim=d.hoje() + timedelta(days=k % 9),
            assinatura=d.hoje() - timedelta(days=k),
        )
        for k in range(1, 41)
    ]
    cliente = d.ClienteFalso(atas, {}, tamanho=3)
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["atas_unicas"] == 40
    assert preparado.contagens["janelas_paginadas"] == 0


async def test_janela_indivisivel_e_paginada_e_a_perda_falha_a_validacao():
    # Mesmo fim e mesma assinatura: só resta paginar, e a sobreposição perde registros.
    cliente = d.ClienteFalso(_mesmo_dia(9), {}, tamanho=3)
    with pytest.raises(ErroValidacao) as erro:
        await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert erro.value.tipo == "total_registros"


async def test_pagina_vazia_no_meio_da_paginacao_falha_sem_publicar(conn_ingest):
    cliente = d.ClienteFalso(_mesmo_dia(4), {}, tamanho=2)
    original = cliente.list_resource

    async def quebrado(rota, **kw):
        resposta = await original(rota, **kw)
        if rota.endswith("1.2_consultarARP_FimVigencia") and kw["pagina"] == 2:
            resposta["resultado"] = []
        return resposta

    cliente.list_resource = quebrado
    with pytest.raises(ErroValidacao) as erro:
        await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert erro.value.tipo == "pagina_vazia"
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 0
    await conn_ingest.commit()


async def test_duplicata_entre_paginas_conta_uma_vez():
    atas = [d.ata(str(n), "Gêneros alimentícios") for n in range(1, 201)]
    atas.append(atas[0])
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, {}))
    assert preparado.contagens["atas_unicas"] == 200
    assert preparado.contagens["atas_declaradas"] == 201


async def test_itens_de_atas_sem_mudanca_sao_reaproveitados(conn_ingest):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 31)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 31)}
    await _carga(conn_ingest, atas, itens)
    anteriores = await arp.carregar_anteriores(conn_ingest)
    assert len(anteriores) == 30

    atas[0] = d.ata("1", "Aquisição de computadores", atualizado="2026-10-13T08:00:00")
    cliente = d.ClienteFalso(atas, itens)
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente, anteriores=anteriores)
    renovar = {
        d.id_ata(str(n)) for n in range(2, 31) if arp.dia_de_renovar(d.id_ata(str(n)), d.hoje())
    }
    buscadas = cliente.chamadas.count(arp.ROTA_ITENS_ATA)
    assert buscadas == 1 + len(renovar)  # a alterada + as do dia de renovar
    assert preparado.contagens["atas_itens_reaproveitados"] == 29 - len(renovar)
    assert preparado.contagens["itens_gravados"] == 30
    await conn_ingest.commit()


async def test_total_declarado_diferente_das_atas_unicas_falha():
    cliente = d.ClienteFalso([d.ata("1", "Aquisição de computadores")], {})
    original = cliente.list_resource

    async def inflado(rota, **kw):
        resposta = await original(rota, **kw)
        if rota.endswith("1.2_consultarARP_FimVigencia") and resposta["resultado"]:
            resposta["totalRegistros"] += 10  # 10 linhas declaradas que nunca chegam
        return resposta

    cliente.list_resource = inflado
    with pytest.raises(ErroValidacao) as erro:
        await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert erro.value.tipo == "total_registros"


async def test_candidatas_sem_item_acima_do_limite_falham():
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 11)]
    with pytest.raises(ErroValidacao) as erro:
        await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, {}))
    assert erro.value.tipo == "itens_ausentes"


async def test_teto_de_requisicoes_interrompe_a_carga():
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 6)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 6)}
    pouco = replace(CONFIG, arp_max_requisicoes=5)
    with pytest.raises(ErroValidacao) as erro:
        await arp.coletar(pouco, d.hoje(), client=d.ClienteFalso(atas, itens))
    assert erro.value.tipo == "teto_requisicoes"


async def test_mudar_o_catalogo_reclassifica(conn_ingest, conn_reader):
    await _carga(conn_ingest)
    await _carga(conn_ingest, pdms=[999])  # PDM 239 deixa de ser TI
    cur = await conn_reader.execute("SELECT id_ata FROM v_atas_ti_vigentes")
    assert [r["id_ata"] for r in await cur.fetchall()] == [d.id_ata("1")]


async def test_leitor_nao_acessa_tabelas_so_views(conn_ingest, conn_reader):
    await _carga(conn_ingest)
    with pytest.raises(InsufficientPrivilege):
        await conn_reader.execute("SELECT * FROM ata_itens")
    await conn_reader.rollback()
    cur = await conn_reader.execute("SELECT count(*) n FROM v_ata_itens_ti")
    assert (await cur.fetchone())["n"] >= 1


async def test_falha_de_publicacao_registra_e_preserva_a_carga_ativa(conn_ingest, monkeypatch):
    await _carga(conn_ingest)
    atas, itens = _cenario()
    preparado, geracao = await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, itens))
    preparado.itens.append(preparado.itens[0])  # chave repetida: viola a PK no COPY
    from uuid import uuid4

    carga = uuid4()
    with pytest.raises(psycopg.errors.Error) as erro:
        await arp._publicar(conn_ingest, preparado, geracao, carga, d.hoje())
    await arp._registrar_falha(conn_ingest, carga, erro.value, geracao, arp.FONTE)
    falha = await _um(
        conn_ingest, "SELECT count(*) n FROM cargas WHERE id = %s AND status = 'falhou'", carga
    )
    assert falha == 1
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 4
    await conn_ingest.commit()


async def test_falha_na_busca_mantem_os_itens_da_carga_anterior(conn_ingest):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 31)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 31)}
    await _carga(conn_ingest, atas, itens)
    anteriores = await arp.carregar_anteriores(conn_ingest)

    atas[0] = d.ata("1", "Aquisição de computadores", atualizado="2026-10-13T08:00:00")
    cliente = d.ClienteFalso(atas, itens)
    original = cliente.list_resource

    async def falha_na_ata_1(rota, **kw):
        if rota == arp.ROTA_ITENS_ATA and kw["numeroControlePncpAta"] == d.id_ata("1"):
            raise ComprasServerError("HTTP 503")
        return await original(rota, **kw)

    cliente.list_resource = falha_na_ata_1
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente, anteriores=anteriores)
    assert preparado.contagens["falhas_busca_itens"] == 1
    assert preparado.contagens["atas_itens_da_carga_anterior_por_falha"] == 1
    assert preparado.contagens["candidatas_sem_item"] == 0
    await conn_ingest.commit()


async def test_soma_das_metades_diferente_do_total_pagina_a_janela():
    # Atas sem data de assinatura somem do filtro por assinatura: a janela inteira é paginada.
    atas = _mesmo_dia(3)
    for bruto in atas[:2]:
        bruto["dataAssinatura"] = ""
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, {}, tamanho=2))
    assert preparado.contagens["janelas_paginadas"] == 1
    assert preparado.contagens["atas_unicas"] == 3


async def test_cache_do_dia_evita_rebuscar_itens_depois_de_uma_falha(tmp_path):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 11)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC", ni=d.CPF_FICTICIO)] for n in range(1, 11)}
    cache = arp.CacheItens.do_dia(d.hoje(), raiz=tmp_path)
    primeiro = d.ClienteFalso(atas, itens)
    await arp.coletar(CONFIG, d.hoje(), client=primeiro, cache=cache)
    assert primeiro.chamadas.count(arp.ROTA_ITENS_ATA) == 10
    assert d.CPF_FICTICIO not in cache.caminho.read_text()
    assert oct(cache.caminho.stat().st_mode)[-3:] == "600"

    with cache.caminho.open("a") as arquivo:
        arquivo.write('{"ata": "trunc')  # queda no meio da escrita
    segundo = d.ClienteFalso(atas, itens)
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=segundo, cache=cache)
    assert segundo.chamadas.count(arp.ROTA_ITENS_ATA) == 0
    assert preparado.contagens["atas_itens_do_cache"] == 10
    assert preparado.contagens["itens_gravados"] == 10


async def test_ata_com_itens_incompletos_conta_como_falha_e_nao_vai_para_o_cache(tmp_path):
    atas = [
        d.ata(str(n), "Aquisição de computadores", assinatura=d.hoje() - timedelta(days=n))
        for n in range(1, 31)
    ]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 31)}
    itens[d.id_ata("1")] = [d.item("1", str(k), "PC") for k in range(1, 6)]
    cliente = d.ClienteFalso(atas, itens, tamanho=2)  # 5 itens em páginas sobrepostas de 2
    cache = arp.CacheItens.do_dia(d.hoje(), raiz=tmp_path)
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente, cache=cache)
    assert preparado.contagens["falhas_busca_itens"] == 1
    assert d.id_ata("1") not in cache.ler()


async def test_cache_de_versao_antiga_da_ata_e_rebuscado(tmp_path):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 11)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 11)}
    cache = arp.CacheItens.do_dia(d.hoje(), raiz=tmp_path)
    await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, itens), cache=cache)
    atas[0] = d.ata("1", "Aquisição de computadores", atualizado="2026-10-13T23:00:00")
    segundo = d.ClienteFalso(atas, itens)
    await arp.coletar(CONFIG, d.hoje(), client=segundo, cache=cache)
    assert segundo.chamadas.count(arp.ROTA_ITENS_ATA) == 1


async def test_fallback_grava_versao_nula_e_a_proxima_carga_rebusca(conn_ingest):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 31)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 31)}
    await _carga(conn_ingest, atas, itens)
    anteriores = await arp.carregar_anteriores(conn_ingest)
    atas[0] = d.ata("1", "Aquisição de computadores", atualizado="2026-10-13T08:00:00")
    cliente = d.ClienteFalso(atas, itens)
    original = cliente.list_resource

    async def falha_na_ata_1(rota, **kw):
        if rota == arp.ROTA_ITENS_ATA and kw["numeroControlePncpAta"] == d.id_ata("1"):
            raise ComprasServerError("HTTP 503")
        return await original(rota, **kw)

    cliente.list_resource = falha_na_ata_1
    preparado, geracao = await arp.coletar(CONFIG, d.hoje(), client=cliente, anteriores=anteriores)
    await arp._publicar(conn_ingest, preparado, geracao, __import__("uuid").uuid4(), d.hoje())
    depois = await arp.carregar_anteriores(conn_ingest)
    assert depois[d.id_ata("1")][0] == ""  # versão desconhecida: nunca bate com a da ata
    proxima = d.ClienteFalso(atas, itens)
    await arp.coletar(CONFIG, d.hoje(), client=proxima, anteriores=depois)
    assert d.id_ata("1") in proxima.buscadas()
    await conn_ingest.commit()


async def test_renovacao_que_falha_e_refeita_no_dia_seguinte_sem_a_ata_mudar(conn_ingest):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 31)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 31)}
    await _carga(conn_ingest, atas, itens)
    anteriores = await arp.carregar_anteriores(conn_ingest)
    alvo = d.id_ata("1")
    dia = next(
        d.hoje() + timedelta(days=k)
        for k in range(7)
        if arp.dia_de_renovar(alvo, d.hoje() + timedelta(days=k))
    )
    seguinte = dia + timedelta(days=1)
    cliente = d.ClienteFalso(atas, itens)
    original = cliente.list_resource

    async def falha_no_alvo(rota, **kw):
        if rota == arp.ROTA_ITENS_ATA and kw["numeroControlePncpAta"] == alvo:
            raise ComprasServerError("HTTP 503")
        return await original(rota, **kw)

    cliente.list_resource = falha_no_alvo
    preparado, geracao = await arp.coletar(CONFIG, dia, client=cliente, anteriores=anteriores)
    assert preparado.contagens["atas_itens_da_carga_anterior_por_falha"] == 1
    await arp._publicar(conn_ingest, preparado, geracao, __import__("uuid").uuid4(), dia)
    depois = await arp.carregar_anteriores(conn_ingest)
    assert not arp.dia_de_renovar(alvo, seguinte)
    proxima = d.ClienteFalso(atas, itens)
    await arp.coletar(CONFIG, seguinte, client=proxima, anteriores=depois)
    assert alvo in proxima.buscadas()  # sem esperar a próxima semana
    await conn_ingest.commit()


COMPRA_PNCP = "00000000000191-1-000010/2026"


def _sem_id(bruto):
    bruto["numeroControlePncpAta"] = None
    bruto["linkAtaPNCP"] = None
    bruto["numeroControlePncpCompra"] = COMPRA_PNCP
    return bruto


def _id_recuperado(seq: int) -> str:
    return f"{COMPRA_PNCP}-{seq:06d}"


def _do_lote(numero_ata: str, id_pncp: str, inicio: str):
    bruto = d.item(numero_ata, "1", "Notebook", nome_pdm="NOTEBOOK")
    bruto.update(
        numeroControlePncpAta=id_pncp,
        codigoUnidadeGerenciadora="999999",
        numeroCompra="00010",
        dataVigenciaInicial=inicio,
    )
    return bruto


async def test_ata_candidata_sem_id_e_recuperada_pelos_itens_e_a_conta_fecha():
    atas = [d.ata(str(n), "Gêneros alimentícios") for n in range(1, 41)]
    atas.append(d.ata("50", "Aquisição de notebooks"))
    atas.append(_sem_id(d.ata("51", "Aquisição de notebooks")))  # candidata: recuperada
    atas.append(_sem_id(d.ata("52", "Gêneros alimentícios")))  # não candidata: só contada
    recuperado = _id_recuperado(51)
    inicio = atas[-1]["dataVigenciaInicial"]
    itens = {
        d.id_ata("50"): [d.item("50", "1", "Notebook")],
        recuperado: [_do_lote("51", recuperado, inicio)],
    }
    cliente = d.ClienteFalso(atas, itens)
    cliente.lote = [_do_lote("51", recuperado, inicio), _do_lote("99", _id_recuperado(99), inicio)]
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    c = preparado.contagens
    assert c["atas_declaradas"] == 43
    assert c["atas_sem_controle_pncp"] == 2
    assert c["atas_sem_id_candidatas"] == 1
    assert c["atas_id_recuperado"] == 1
    assert c["atas_unicas"] == 42
    assert recuperado in {a.id_origem for a in preparado.atas}
    assert recuperado in cliente.buscadas()
    assert preparado.decisoes[recuperado][0]  # TI pelo objeto


async def test_recuperacao_que_falha_conta_e_nao_derruba_a_carga():
    atas = [d.ata(str(n), "Gêneros alimentícios") for n in range(1, 41)]
    atas.append(d.ata("50", "Aquisição de notebooks"))
    atas.append(_sem_id(d.ata("51", "Aquisição de notebooks")))
    cliente = d.ClienteFalso(atas, {d.id_ata("50"): [d.item("50", "1", "Notebook")]})
    original = cliente.list_resource

    async def lote_fora(rota, **kw):
        if rota == arp.ROTA_ITENS_LOTE:
            raise ComprasServerError("HTTP 503")
        return await original(rota, **kw)

    cliente.list_resource = lote_fora
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["falhas_recuperacao_id"] == 1
    assert preparado.contagens["atas_id_recuperado"] == 0
    assert preparado.contagens["atas_unicas"] == 41


async def test_numero_com_dois_ids_nos_itens_nao_e_recuperado():
    atas = [d.ata(str(n), "Gêneros alimentícios") for n in range(1, 41)]
    atas.append(d.ata("50", "Aquisição de notebooks"))
    atas.append(_sem_id(d.ata("51", "Aquisição de notebooks")))
    inicio = atas[-1]["dataVigenciaInicial"]
    cliente = d.ClienteFalso(atas, {d.id_ata("50"): [d.item("50", "1", "Notebook")]})
    cliente.lote = [
        _do_lote("51", _id_recuperado(1), inicio),
        _do_lote("51", _id_recuperado(2), inicio),
    ]
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["atas_id_recuperado"] == 0


def _base_sem_id():
    atas = [d.ata(str(n), "Gêneros alimentícios") for n in range(1, 41)]
    atas.append(d.ata("50", "Aquisição de notebooks"))
    return atas, {d.id_ata("50"): [d.item("50", "1", "Notebook")]}


async def test_linha_do_lote_de_outro_grupo_ou_outra_compra_nao_e_usada():
    atas, itens = _base_sem_id()
    atas.append(_sem_id(d.ata("51", "Aquisição de notebooks")))
    inicio = atas[-1]["dataVigenciaInicial"]
    outra_compra = _do_lote("51", _id_recuperado(7), inicio)
    outra_compra["numeroCompra"] = "00099"  # a API ignorou o filtro de compra
    de_outra_compra_pncp = _do_lote("51", "00000000000191-1-000077/2026-000001", inicio)
    cliente = d.ClienteFalso(atas, itens)
    original = cliente.list_resource

    async def ignora_filtro(rota, **kw):
        if rota == arp.ROTA_ITENS_LOTE:
            return d.envelope([outra_compra])
        return await original(rota, **kw)

    cliente.list_resource = ignora_filtro
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["atas_id_recuperado"] == 0
    cliente.list_resource = original
    cliente.lote = [de_outra_compra_pncp]  # id que não começa pelo id da compra da ata
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["atas_id_recuperado"] == 0


async def test_duas_atas_sem_id_que_levam_ao_mesmo_id_nao_sao_recuperadas():
    atas, itens = _base_sem_id()
    a = _sem_id(d.ata("51", "Aquisição de notebooks"))
    b = _sem_id(d.ata("52", "Aquisição de notebooks", inicio=d.hoje() - timedelta(days=20)))
    atas += [a, b]
    cliente = d.ClienteFalso(atas, itens)
    cliente.lote = [
        _do_lote("51", _id_recuperado(5), a["dataVigenciaInicial"]),
        _do_lote("52", _id_recuperado(5), b["dataVigenciaInicial"]),
    ]
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["atas_id_recuperado"] == 0


async def test_dia_cheio_que_cai_na_paginacao_conta_cada_linha_uma_vez():
    # Dia cheio com uma ata sem assinatura (força paginar o dia) e uma linha descartada
    # (início inválido): as fatias por assinatura não podem ser contadas de novo.
    atas = _mesmo_dia(6)
    for k, bruto in enumerate(atas):
        bruto["dataAssinatura"] = (d.hoje() - timedelta(days=10 + k)).isoformat()
    atas[0]["dataAssinatura"] = ""
    atas[1]["dataVigenciaInicial"] = "2026-02-31"
    cliente = d.ClienteFalso(atas, {}, tamanho=5)
    listagem = await arp.listar_atas(cliente, arp._Orcamento(1000.0, 5000), d.hoje())
    assert listagem.paginadas >= 1
    assert listagem.descartadas == 1
    assert listagem.explicadas == listagem.declarado == 6
    assert len(listagem.atas) == 5


@pytest.mark.parametrize(
    ("tipo", "saida"),
    [
        ("total_registros", 2),
        ("contrato", 2),
        ("envelope", 2),
        ("listagem_inconsistente", 1),
        ("teto_requisicoes", 1),
    ],
)
def test_codigo_de_saida_separa_erro_deterministico(tipo, saida):
    assert arp.codigo_saida(ErroValidacao(tipo, "x")) == saida


async def test_atas_sem_id_acima_do_limite_falham_como_mudanca_da_api():
    atas = [d.ata(str(n), "Gêneros alimentícios") for n in range(1, 11)]
    atas += [_sem_id(d.ata(str(n), "Gêneros alimentícios")) for n in range(11, 14)]
    with pytest.raises(ErroValidacao) as erro:
        await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, {}))
    assert erro.value.tipo == "sem_id_excessivo"


async def test_id_repetido_com_excluida_mantem_a_vigente_e_conflito_e_contado():
    atas = [d.ata(str(n), "Gêneros alimentícios") for n in range(1, 201)]
    atas.append(d.ata("1", "Gêneros alimentícios", excluida=True, atualizado="2026-10-02T00:00:00"))
    outra = d.ata("2", "Material de limpeza")
    outra["numeroAtaRegistroPreco"] = "00099/2026"  # ata diferente, mesmo id
    atas.append(outra)
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, {}))
    assert preparado.contagens["atas_id_repetido"] == 2
    assert preparado.contagens["atas_conflito_id"] == 1
    vigentes = {a.id_origem: a.vigente_na_origem for a in preparado.atas}
    assert vigentes[d.id_ata("1")]


async def test_listagem_adaptativa_traz_tudo_uma_vez_com_poucas_consultas():
    # 600 atas: dias cheios (até 12 por dia, página de 10), assinaturas variadas e um ano
    # seguinte quase vazio. Nenhuma pode faltar nem exigir paginação.
    atas = [
        d.ata(
            str(k),
            "Gêneros alimentícios",
            fim=d.hoje() + timedelta(days=k % 50 if k < 590 else 400 + k % 10),
            assinatura=d.hoje() - timedelta(days=300 + k % 7),
        )
        for k in range(1, 601)
    ]
    cliente = d.ClienteFalso(atas, {}, tamanho=10)
    listagem = await arp.listar_atas(cliente, arp._Orcamento(1000.0, 5000), d.hoje())
    assert len(listagem.atas) == 600
    assert listagem.declarado == 600
    assert listagem.paginadas == 0
    assert listagem.requisicoes < 300  # a bissecção antiga gastava 593 aqui


async def test_checkpoint_sem_formato_ou_sem_versao_e_ignorado(tmp_path):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 11)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 11)}
    cache = arp.CacheItens.do_dia(d.hoje(), raiz=tmp_path)
    await arp.coletar(CONFIG, d.hoje(), client=d.ClienteFalso(atas, itens), cache=cache)
    linhas = cache.caminho.read_text().splitlines()
    import json

    legadas = []
    for linha in linhas[:2]:
        registro = json.loads(linha)
        registro.pop("formato")
        legadas.append(registro)
    registro = json.loads(linhas[2])
    registro["versao"] = None
    legadas.append(registro)
    cache.caminho.write_text(
        "\n".join([json.dumps(r) for r in legadas] + linhas[3:]) + "\n", encoding="utf-8"
    )
    segundo = d.ClienteFalso(atas, itens)
    await arp.coletar(CONFIG, d.hoje(), client=segundo, cache=cache)
    assert sorted(segundo.buscadas()) == sorted(r["ata"] for r in legadas)


async def test_itens_com_total_que_muda_entre_paginas_contam_como_falha(tmp_path):
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 31)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 31)}
    itens[d.id_ata("1")] = [d.item("1", str(k), "PC") for k in range(1, 4)]
    cliente = d.ClienteFalso(atas, itens)
    original = cliente.list_resource

    async def lista_mudando(rota, **kw):
        if rota == arp.ROTA_ITENS_ATA and kw["numeroControlePncpAta"] == d.id_ata("1"):
            # 1ª página declara 5 itens em 3 páginas; a 2ª, 3 itens em 2 (cenário do Codex).
            todos = itens[d.id_ata("1")]
            if kw["pagina"] == 1:
                return d.envelope(todos[:2], total=5, paginas=3)
            return d.envelope(todos[2:], total=3, paginas=2)
        return await original(rota, **kw)

    cliente.list_resource = lista_mudando
    cache = arp.CacheItens.do_dia(d.hoje(), raiz=tmp_path)
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente, cache=cache)
    assert preparado.contagens["falhas_busca_itens"] == 1
    assert d.id_ata("1") not in cache.ler()


async def test_lote_incompleto_nao_recupera_id_e_conta_falha():
    # O lote declara 2 linhas (dois ids para o mesmo número), mas só 1 chega: nada é aceito.
    atas, itens = _base_sem_id()
    atas.append(_sem_id(d.ata("51", "Aquisição de notebooks")))
    inicio = atas[-1]["dataVigenciaInicial"]
    cliente = d.ClienteFalso(atas, itens)
    original = cliente.list_resource

    async def lote_que_omite(rota, **kw):
        if rota == arp.ROTA_ITENS_LOTE:
            return d.envelope([_do_lote("51", _id_recuperado(1), inicio)], total=2)
        return await original(rota, **kw)

    cliente.list_resource = lote_que_omite
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["atas_id_recuperado"] == 0
    assert preparado.contagens["falhas_recuperacao_id"] == 1


async def test_ata_sem_id_repetida_fica_com_a_linha_vigente():
    atas, itens = _base_sem_id()
    atas += [d.ata(str(n), "Gêneros alimentícios") for n in range(100, 260)]  # repetida < 1%
    excluida = _sem_id(d.ata("51", "Aquisição de notebooks", excluida=True))
    vigente = _sem_id(d.ata("51", "Aquisição de notebooks", atualizado="2026-09-01T00:00:00"))
    atas += [excluida, vigente]
    inicio = vigente["dataVigenciaInicial"]
    recuperado = _id_recuperado(51)
    itens[recuperado] = [_do_lote("51", recuperado, inicio)]
    cliente = d.ClienteFalso(atas, itens)
    cliente.lote = [_do_lote("51", recuperado, inicio)]
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    ata = next(a for a in preparado.atas if a.id_origem == recuperado)
    assert ata.vigente_na_origem


async def test_paginacao_com_total_que_muda_no_meio_falha_a_listagem():
    cliente = d.ClienteFalso(_mesmo_dia(6), {}, tamanho=5)
    original = cliente.list_resource

    async def crescendo(rota, **kw):
        resposta = await original(rota, **kw)
        if rota.endswith("1.2_consultarARP_FimVigencia") and kw["pagina"] == 2:
            resposta["totalRegistros"] += 3
            resposta["totalPaginas"] += 1
        return resposta

    cliente.list_resource = crescendo
    with pytest.raises(ErroValidacao) as erro:
        await arp.listar_atas(cliente, arp._Orcamento(1000.0, 5000), d.hoje())
    assert erro.value.tipo == "listagem_inconsistente"


async def test_lote_com_cpfs_de_mesma_mascara_nao_e_falsa_incompletude():
    atas, itens = _base_sem_id()
    atas.append(_sem_id(d.ata("51", "Aquisição de notebooks")))
    inicio = atas[-1]["dataVigenciaInicial"]
    recuperado = _id_recuperado(51)
    # Mesmos dígitos visíveis na máscara, documentos diferentes.
    um = _do_lote("51", recuperado, inicio)
    um["niFornecedor"] = "12345678909"
    outro = _do_lote("51", recuperado, inicio)
    outro["niFornecedor"] = "12345600909"
    itens[recuperado] = [um]
    cliente = d.ClienteFalso(atas, itens)
    cliente.lote = [um, outro]
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.contagens["atas_id_recuperado"] == 1
    assert preparado.contagens["falhas_recuperacao_id"] == 0


async def test_item_reincluido_duplicado_na_origem_nao_e_falsa_incompletude(tmp_path):
    # A API devolve o mesmo item duas vezes, diferindo só em dataHoraInclusao/Atualizacao
    # (14/10/2026): a ata veio completa, entra uma vez e vai para o checkpoint.
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 11)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 11)}
    velho, novo = dict(itens[d.id_ata("1")][0]), dict(itens[d.id_ata("1")][0])
    velho.update(dataHoraInclusao="2026-08-31T09:55:27", dataHoraAtualizacao="2026-08-31T09:55:27")
    novo.update(dataHoraInclusao="2026-09-03T07:45:06", dataHoraAtualizacao="2026-09-03T07:45:06")
    novo["valorUnitario"] = 99.0
    itens[d.id_ata("1")] = [velho, novo]
    cache = arp.CacheItens.do_dia(d.hoje(), raiz=tmp_path)
    preparado, _ = await arp.coletar(
        CONFIG, d.hoje(), client=d.ClienteFalso(atas, itens), cache=cache
    )
    assert preparado.contagens["falhas_busca_itens"] == 0
    do_cache = cache.ler()[d.id_ata("1")][1]
    assert len(do_cache) == 1
    assert do_cache[0].valor_unitario == 99  # ficou a reinclusão mais nova


async def test_linha_atualizada_entre_paginas_nao_esconde_linha_omitida(tmp_path):
    # Revisão 5 do Codex: a página 2 repete o item da página 1 com outra dataHoraAtualizacao e
    # o segundo item declarado nunca chega. Tem de ser falha, não checkpoint "completo".
    atas = [d.ata(str(n), "Aquisição de computadores") for n in range(1, 31)]
    itens = {d.id_ata(str(n)): [d.item(str(n), "1", "PC")] for n in range(1, 31)}
    cliente = d.ClienteFalso(atas, itens)
    original = cliente.list_resource
    v1 = dict(d.item("1", "1", "PC"), dataHoraAtualizacao="2026-10-14T08:00:00")
    v2 = dict(v1, dataHoraAtualizacao="2026-10-14T08:00:05", quantidadeEmpenhada=3.0)

    async def pagina_repetida(rota, **kw):
        if rota == arp.ROTA_ITENS_ATA and kw["numeroControlePncpAta"] == d.id_ata("1"):
            linha = v1 if kw["pagina"] == 1 else v2
            return d.envelope([linha], total=2, paginas=2)
        return await original(rota, **kw)

    cliente.list_resource = pagina_repetida
    cache = arp.CacheItens.do_dia(d.hoje(), raiz=tmp_path)
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente, cache=cache)
    assert preparado.contagens["falhas_busca_itens"] == 1
    assert d.id_ata("1") not in cache.ler()


def _lote_pdm(numero: str, n_item: str, pdm: int, inicio):
    return {
        **d.item(numero, n_item, f"Item {n_item}", pdm=pdm, nome_pdm=f"PDM {pdm}"),
        "dataVigenciaInicial": inicio.isoformat(),
    }


def _cenario_varredura():
    """Atas de objeto genérico: uma central, uma incidental (1 de 6) e uma na proporção (1 de 2)."""
    atas = [
        d.ata("10", "Material de expediente"),
        d.ata("11", "Material de consumo diverso"),
        d.ata("12", "Insumos diversos"),
    ]
    atas[1]["quantidadeItens"] = 6
    inicio = d.hoje() - timedelta(days=30)
    itens = {
        d.id_ata("10"): [d.item("10", "1", "Item central", pdm=8435, nome_pdm="PRODUTO CENTRAL")],
        d.id_ata("11"): [
            d.item("11", "1", "Mouse pad", pdm=283),
            *(d.item("11", str(n), "Caneta", pdm=77) for n in (2, 3, 4, 5, 6)),
        ],
        d.id_ata("12"): [
            d.item("12", "1", "Teclado", pdm=283),
            d.item("12", "2", "Caneta", pdm=77),
        ],
    }
    lote = [
        _lote_pdm("10", "1", 8435, inicio),
        _lote_pdm("11", "1", 283, inicio),
        _lote_pdm("12", "1", 283, inicio),
    ]
    return atas, itens, lote


def _cliente_varredura():
    atas, itens, lote = _cenario_varredura()
    cliente = d.ClienteFalso(atas, itens, pdms=[283, 8435])
    cliente.lote = lote
    return cliente


def _chamadas_por_pdm(cliente) -> int:
    return sum(1 for rota, f in cliente.filtros if rota == arp.ROTA_ITENS_LOTE and "codigoPdm" in f)


async def test_varredura_acha_ata_de_objeto_generico_e_corta_a_incidental():
    cliente = _cliente_varredura()
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    decisoes = preparado.decisoes
    assert decisoes[d.id_ata("10")][0] and decisoes[d.id_ata("10")][1].endswith(":central")
    assert decisoes[d.id_ata("12")][0] and decisoes[d.id_ata("12")][1].endswith(":prop1de2")
    assert not decisoes[d.id_ata("11")][0]  # 1 de 6 itens, nenhum central
    assert decisoes[d.id_ata("11")][1] == "catalogo_incidental"
    assert d.id_ata("11") in cliente.buscadas()  # sem pré-corte: o corte final usa os itens reais
    c = preparado.contagens
    assert c["varredura_atas"] == 3 and c["varredura_candidatas_novas"] == 3
    assert c["atas_incidentais"] == 1 and c["varredura_falhas"] == 0


async def test_varredura_completa_nao_repete_nas_noites_seguintes(tmp_path):
    cache = arp.CacheVarredura.do_ciclo(d.hoje(), tmp_path)
    primeiro = _cliente_varredura()
    await arp.coletar(CONFIG, d.hoje(), client=primeiro, cache_varredura=cache)
    assert cache.caminho.is_file() and oct(cache.caminho.stat().st_mode)[-3:] == "600"
    assert _chamadas_por_pdm(primeiro) >= 2  # 2 PDMs x ao menos 1 janela
    segundo = _cliente_varredura()
    cache = arp.CacheVarredura.do_ciclo(d.hoje() + timedelta(days=1), tmp_path)
    preparado, _ = await arp.coletar(
        CONFIG, d.hoje() + timedelta(days=1), client=segundo, cache_varredura=cache
    )
    assert _chamadas_por_pdm(segundo) == 0  # ciclo completo: zero requisições de varredura
    assert preparado.contagens["varredura_completa"] == 1
    assert preparado.decisoes[d.id_ata("10")][0]  # o cache continua alimentando as candidatas


async def test_varredura_respeita_o_prazo_mas_todo_ciclo_avanca_um_par_por_noite(tmp_path):
    cache = arp.CacheVarredura.do_ciclo(d.hoje(), tmp_path)
    config = replace(CONFIG, arp_varredura_minutos=1e-9)  # prazo já vencido
    pouco_tempo = _cliente_varredura()
    preparado, _ = await arp.coletar(config, d.hoje(), client=pouco_tempo, cache_varredura=cache)
    assert _chamadas_por_pdm(pouco_tempo) == 1  # só o 1º par (PDM central primeiro)
    assert preparado.contagens["varredura_pendentes"] >= 1
    assert preparado.contagens["varredura_completa"] == 0
    assert preparado.decisoes[d.id_ata("10")][0]  # o PDM central é o 1º da ordem
    assert d.id_ata("12") not in {i for i, (ti, _) in preparado.decisoes.items() if ti}
    # Na noite seguinte há tempo: termina e fecha o ciclo.
    retomada = _cliente_varredura()
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=retomada, cache_varredura=cache)
    assert _chamadas_por_pdm(retomada) == 1  # só o par que faltava
    assert preparado.contagens["varredura_pendentes"] == 0
    assert preparado.decisoes[d.id_ata("12")][0]
    assert '"completa": true' in cache.caminho.read_text(encoding="utf-8")


async def test_prazo_vale_no_meio_de_um_par_paginado_depois_do_primeiro_par(monkeypatch):
    cliente = d.ClienteFalso([], {}, pdms=[8435, 283], tamanho=2)  # cada resposta tem 2 registros
    dia = d.hoje() - timedelta(days=30)
    cliente.lote = [_lote_pdm(str(n), "1", pdm, dia) for n in range(8) for pdm in (8435, 283)]
    concluidos = []
    # O 1º par roda sem prazo; o 2º estoura depois da sua 1ª requisição e não pode ser gravado.
    relogio = iter([0.0, 10_000.0])
    monkeypatch.setattr(arp, "time", SimpleNamespace(monotonic=lambda: next(relogio, 10_000.0)))
    varredura = await arp.varrer_pdm(
        cliente,
        arp._Orcamento(1000.0, 1000),
        [8435, 283],
        arp.janelas_do_ciclo(d.hoje(), 1),
        ao_concluir=lambda pdm, *a: concluidos.append(pdm),
        prazo=1.0,
    )
    assert concluidos == [8435] and varredura.pendentes == 1
    assert {p for _, itens in varredura.itens.items() for p, _ in itens} == {8435}


async def test_varredura_parcial_retoma_so_os_pares_que_faltam(tmp_path):
    cache = arp.CacheVarredura.do_ciclo(d.hoje(), tmp_path)
    cliente = _cliente_varredura()
    original = cliente.list_resource
    falhou = {"uma_vez": False}

    async def uma_falha(rota, **kw):
        if rota == arp.ROTA_ITENS_LOTE and kw.get("codigoPdm") == 8435 and not falhou["uma_vez"]:
            falhou["uma_vez"] = True
            raise ComprasServerError("HTTP 503")
        return await original(rota, **kw)

    cliente.list_resource = uma_falha
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente, cache_varredura=cache)
    assert preparado.contagens["varredura_falhas"] == 1
    assert '"completa"' not in cache.caminho.read_text(encoding="utf-8")  # ciclo incompleto
    segundo = _cliente_varredura()
    await arp.coletar(CONFIG, d.hoje(), client=segundo, cache_varredura=cache)
    pares = {
        f["codigoPdm"] for r, f in segundo.filtros if r == arp.ROTA_ITENS_LOTE and "codigoPdm" in f
    }
    assert pares == {8435}  # só o PDM que falhou volta a ser consultado
    assert '"completa": true' in cache.caminho.read_text(encoding="utf-8")


async def test_varredura_que_falha_nao_derruba_a_carga(tmp_path):
    cache = arp.CacheVarredura.do_ciclo(d.hoje(), tmp_path)
    cliente = _cliente_varredura()
    original = cliente.list_resource

    async def sem_lote_por_pdm(rota, **kw):
        if rota == arp.ROTA_ITENS_LOTE and "codigoPdm" in kw:
            raise ComprasServerError("HTTP 503")
        return await original(rota, **kw)

    cliente.list_resource = sem_lote_por_pdm
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente, cache_varredura=cache)
    assert preparado.contagens["varredura_falhas"] > 0
    assert preparado.contagens["atas_unicas"] == 3  # a carga segue; só as candidatas diminuem


async def test_varredura_parcial_nao_derruba_ata_que_ja_era_candidata():
    """Revisão do Codex: sem varredura, quem já tinha itens na carga anterior continua avaliada."""
    cliente = _cliente_varredura()
    itens_anteriores = [arp.mapear_item(i) for i in cliente.itens[d.id_ata("10")]]
    atas, _, _ = _cenario_varredura()
    versao = atas[0]["dataHoraAtualizacao"]
    anteriores = {d.id_ata("10"): (versao, itens_anteriores)}
    config = replace(CONFIG, arp_varredura_minutos=1e-9)  # varredura sem tempo algum
    preparado, _ = await arp.coletar(
        config, d.hoje(), client=cliente, anteriores=anteriores, cache_varredura=None
    )
    assert preparado.decisoes[d.id_ata("10")][0]  # segue TI pelo PDM central dos itens anteriores


async def test_contagem_da_listagem_divergente_nao_perde_ata_porque_o_corte_usa_itens_reais():
    """Revisão do Codex: 1 de 2 itens reais, mas a listagem diz 5 itens: não há pré-corte pela
    contagem da listagem, então a ata é conferida e passa no corte real de 1/2."""
    atas = [d.ata("20", "Insumos gerais")]
    atas[0]["quantidadeItens"] = 5
    itens = {
        d.id_ata("20"): [d.item("20", "1", "Teclado", pdm=283), d.item("20", "2", "Caneta", pdm=77)]
    }
    cliente = d.ClienteFalso(atas, itens, pdms=[283, 8435])
    cliente.lote = [_lote_pdm("20", "1", 283, d.hoje() - timedelta(days=30))]
    preparado, _ = await arp.coletar(CONFIG, d.hoje(), client=cliente)
    assert preparado.decisoes[d.id_ata("20")][0]
    assert preparado.decisoes[d.id_ata("20")][1].endswith(":prop1de2")


async def test_janela_que_pagina_e_partida_ate_caber_numa_pagina(tmp_path):
    cliente = _cliente_varredura()
    cliente.tamanho = 3
    inicio = d.hoje() - timedelta(days=40)
    cliente.lote = [  # 6 itens de um PDM em dias diferentes: uma janela só paginaria e perderia
        _lote_pdm(str(30 + n), "1", 8435, inicio + timedelta(days=n * 6)) for n in range(6)
    ]
    cliente.atas = [d.ata(str(30 + n), "Insumos gerais") for n in range(6)]
    varredura = await arp.varrer_pdm(
        cliente,
        arp._Orcamento(1000.0, 1000),
        [8435],
        arp.janelas_do_ciclo(d.hoje(), 1),
    )
    assert len(varredura.itens) == 6  # nenhum perdido na fronteira de página
    assert varredura.incompletas == 0


async def test_janela_de_um_dia_que_ainda_pagina_fica_marcada_como_incompleta():
    cliente = _cliente_varredura()
    cliente.tamanho = 2
    dia = d.hoje() - timedelta(days=10)
    cliente.lote = [_lote_pdm(str(40 + n), "1", 8435, dia) for n in range(5)]  # tudo no mesmo dia
    varredura = await arp.varrer_pdm(
        cliente, arp._Orcamento(1000.0, 1000), [8435], arp.janelas_do_ciclo(d.hoje(), 1)
    )
    assert varredura.incompletas >= 1
    assert varredura.itens  # o que veio fica; o relatório mostra a lacuna


def test_cache_cola_nova_linha_depois_de_cauda_truncada_e_nao_aceita_completa_sem_pares(tmp_path):
    cache = arp.CacheVarredura.do_ciclo(d.hoje(), tmp_path)
    cache.iniciar("v1", d.hoje(), 1)
    cache.gravar_par(8435, 0, [(d.id_ata("10"), "1")], "NOTEBOOK", False)
    with cache.caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write('{"pdm": 283, "k"')  # queda no meio da escrita, sem quebra de linha
    cache.gravar_par(283, 0, [(d.id_ata("11"), "1")], "MOUSE", False)  # não pode colar na cauda
    _, _, feitos, progresso, _ = cache.ler("v1")
    assert feitos == {(8435, 0), (283, 0)}
    assert progresso.nomes == {8435: "NOTEBOOK", 283: "MOUSE"}


def test_cache_de_outra_versao_do_catalogo_ou_corrompido_recomeca(tmp_path):
    cache = arp.CacheVarredura.do_ciclo(d.hoje(), tmp_path)
    cache.iniciar("catalogo-antigo", d.hoje(), 3)
    cache.gravar_par(8435, 0, [(d.id_ata("10"), "1")], "NOTEBOOK", True)
    assert cache.ler("catalogo-novo") is None
    ancora, janelas, feitos, progresso, completa = cache.ler("catalogo-antigo")
    assert (ancora, janelas, feitos, completa) == (d.hoje(), 3, {(8435, 0)}, False)
    assert progresso.itens == {d.id_ata("10"): {(8435, "1")}} and progresso.incompletas == 1
    cache.caminho.write_text("lixo", encoding="utf-8")
    assert cache.ler("catalogo-antigo") is None


def test_ciclo_incompleto_atravessa_a_semana_e_completo_so_recomeca_depois_de_7_dias(tmp_path):
    hoje = d.hoje()
    primeiro = arp.CacheVarredura.do_ciclo(hoje, tmp_path)
    primeiro.iniciar("v1", hoje, 2)
    # Incompleto: continua o mesmo arquivo mesmo semanas depois (o progresso não se perde).
    assert (
        arp.CacheVarredura.do_ciclo(hoje + timedelta(days=20), tmp_path).caminho == primeiro.caminho
    )
    primeiro.marcar_completa()
    assert (
        arp.CacheVarredura.do_ciclo(hoje + timedelta(days=6), tmp_path).caminho == primeiro.caminho
    )
    novo = arp.CacheVarredura.do_ciclo(hoje + timedelta(days=7), tmp_path)
    assert novo.caminho != primeiro.caminho and novo.caminho.name.startswith("varredura-")


def test_completa_sem_todos_os_pares_nao_vale(tmp_path):
    """O marcador `completa` sozinho (par perdido por truncamento) não fecha o ciclo."""
    cache = arp.CacheVarredura.do_ciclo(d.hoje(), tmp_path)
    cache.iniciar("v1", d.hoje(), 1)
    cache.marcar_completa()
    ancora, janelas, feitos, _, completa = cache.ler("v1")
    esperados = {(p, k) for p in (283, 8435) for k in range(janelas)}
    assert completa and not esperados <= feitos


def test_cache_nao_segue_link_simbolico(tmp_path):
    alvo = tmp_path / "alheio.txt"
    alvo.write_text("nao mexer", encoding="utf-8")
    cache = arp.CacheVarredura(tmp_path / "varredura-2026-10-16.jsonl")
    cache.caminho.symlink_to(alvo)
    with pytest.raises(OSError):
        cache.iniciar("v1", d.hoje(), 1)
    assert alvo.read_text(encoding="utf-8") == "nao mexer"


def test_janelas_do_ciclo_nao_sobrepoem_e_cobrem_ate_o_inicio_mais_antigo():
    ancora = d.hoje()
    janelas = arp.janelas_do_ciclo(ancora, 3)
    assert janelas[0][2] == ancora + timedelta(days=6)
    for (_, ini_a, _), (_, _, fim_b) in zip(janelas, janelas[1:], strict=False):
        assert fim_b == ini_a - timedelta(days=1)
    assert all((fim - ini).days == 364 for _, ini, fim in janelas)
    antigo = ancora - timedelta(days=500)
    n = arp.quantidade_de_janelas(ancora, antigo)
    assert arp.janelas_do_ciclo(ancora, n)[-1][1] <= antigo
    assert arp.quantidade_de_janelas(ancora, None) == 1
