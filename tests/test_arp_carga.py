"""Carga ARP no Postgres: troca atômica, idempotência, falhas, privacidade e permissões."""

from dataclasses import replace
from datetime import timedelta

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
    assert motivos[d.id_ata("2")] == "catmat70:pdm239@item"
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
