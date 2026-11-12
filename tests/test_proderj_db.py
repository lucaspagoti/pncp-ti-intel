"""Links do PRODERJ no banco (migração 0012, ADR 0042): normalização, view, troca e permissões."""

from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
import web_dados
from proderj_dados import CASOS_PROCESSO

from pncp_ti.busca import atualizar_busca
from pncp_ti.config import get_settings, web_dsn
from pncp_ti.fontes import proderj
from pncp_ti.fontes.siga_csv import ErroValidacao

MICROSOFT = "SEI-430002/000030/2024"
SEM_PAGINA = "SEI-430002/009999/2025"


def link(processo: str, node: int, lista: str = "homologadas") -> proderj.Link:
    return proderj.Link(
        proderj.normalizar_processo(processo),
        node,
        proderj.URL_NODE.format(node),
        f"título {node}",
        lista,
    )


@pytest.fixture
async def siga(conn_ingest):
    carga = uuid4()
    comandos = [
        (
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
            "VALUES (%s, 'siga_rj', %s, 'concluida', true)",
            (carga, web_dados.HOJE),
        ),
        web_dados.ata_proderj(carga, "P1", "MICROSOFT", MICROSOFT),
        web_dados.ata_proderj(carga, "P2", "OUTSOURCING", "430002/000055/2024"),
        web_dados.ata_proderj(carga, "P3", "SEM PÁGINA NO SITE", SEM_PAGINA),
        web_dados.ata_proderj(carga, "P4", "SEM PROCESSO", None),
        web_dados.ata(carga, "S9", "Ata de outro órgão", orgao="SEFAZ"),
        web_dados.REFRESH,
    ]
    for comando, parametros in comandos:
        await conn_ingest.execute(comando, parametros)
    await conn_ingest.commit()


async def view(nome_banco_teste: str) -> dict[str, str | None]:
    """O que a web lê: `v_ata_proderj` pelo papel `web_reader`."""
    dsn = web_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        linhas = await (await conn.execute("SELECT id_ata, url FROM v_ata_proderj")).fetchall()
    return dict(linhas)


@pytest.mark.parametrize(("texto", "esperado"), CASOS_PROCESSO)
async def test_funcao_sql_normaliza_como_o_python(conn_ingest, texto, esperado):
    linha = await (
        await conn_ingest.execute("SELECT proderj_processo(%s) AS p", (texto,))
    ).fetchone()
    assert linha["p"] == esperado == proderj.normalizar_processo(texto)


async def test_view_casa_o_processo_e_deixa_url_nula_sem_pagina(
    conn_ingest, siga, nome_banco_teste
):
    links = {
        k.processo: k
        for k in (link(MICROSOFT, 1779), link("430002/000055/2024", 1777, "realizadas"))
    }
    await proderj.publicar(conn_ingest, links, 2, uuid4())
    achados = await view(nome_banco_teste)
    assert achados == {
        "P1": "https://www.rj.gov.br/proderj/node/1779",
        "P2": "https://www.rj.gov.br/proderj/node/1777",
        "P3": None,  # consta no SIGA, não consta no site
        "P4": None,  # ata sem processo
    }  # a ata de outro órgão (S9) não entra


async def test_sem_carga_do_site_todas_ficam_sem_link(conn_ingest, siga, nome_banco_teste):
    assert set((await view(nome_banco_teste)).values()) == {None}


async def test_nova_carga_troca_a_anterior_e_so_a_ativa_vale(conn_ingest, siga, nome_banco_teste):
    await proderj.publicar(
        conn_ingest, {link(MICROSOFT, 1779).processo: link(MICROSOFT, 1779)}, 1, uuid4()
    )
    novo = link(MICROSOFT, 1800)
    await proderj.publicar(conn_ingest, {novo.processo: novo}, 1, uuid4())
    assert (await view(nome_banco_teste))["P1"].endswith("/node/1800")
    n = await (await conn_ingest.execute("SELECT count(*) AS n FROM proderj_links")).fetchone()
    assert n["n"] == 1  # a carga substituída não deixa linhas
    ativas = await (
        await conn_ingest.execute(
            "SELECT count(*) AS n FROM cargas WHERE fonte='proderj' AND ativa"
        )
    ).fetchone()
    assert ativas["n"] == 1


async def test_queda_brusca_nao_publica_e_mantem_os_links(conn_ingest, siga, nome_banco_teste):
    muitos = {k.processo: k for k in (link(f"430002/{n:06}/2024", 100 + n) for n in range(1, 11))}
    muitos[link(MICROSOFT, 1779).processo] = link(MICROSOFT, 1779)
    await proderj.publicar(conn_ingest, muitos, 11, uuid4())
    poucos = {link(MICROSOFT, 1800).processo: link(MICROSOFT, 1800)}
    with pytest.raises(ErroValidacao) as erro:
        await proderj.publicar(conn_ingest, poucos, 1, uuid4())
    assert erro.value.tipo == "queda_volume"
    assert (await view(nome_banco_teste))["P1"].endswith("/node/1779")


async def test_carga_que_falha_fica_registrada_e_nao_troca_nada(
    conn_ingest, siga, nome_banco_teste, monkeypatch
):
    ativo = link(MICROSOFT, 1779)
    await proderj.publicar(conn_ingest, {ativo.processo: ativo}, 1, uuid4())

    async def site_fora_do_ar(client):
        raise ErroValidacao("rede", "site fora do ar")

    monkeypatch.setattr(proderj, "ler_site", site_fora_do_ar)
    with pytest.raises(ErroValidacao):
        await proderj.carregar(conn_ingest, None)
    falha = await (
        await conn_ingest.execute(
            "SELECT status, erro_tipo FROM cargas WHERE fonte='proderj' AND status='falhou'"
        )
    ).fetchone()
    assert falha == {"status": "falhou", "erro_tipo": "rede"}
    assert (await view(nome_banco_teste))["P1"].endswith("/node/1779")


async def test_rodape_dados_de_nao_lista_o_proderj(conn_ingest, siga, nome_banco_teste):
    await proderj.publicar(
        conn_ingest, {link(MICROSOFT, 1779).processo: link(MICROSOFT, 1779)}, 1, uuid4()
    )
    dsn = web_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        fontes = {
            r[0] for r in await (await conn.execute("SELECT fonte FROM v_cargas_web")).fetchall()
        }
    assert "proderj" not in fontes and "siga_rj" in fontes


async def test_web_reader_le_so_a_view_nao_a_tabela(nome_banco_teste):
    dsn = web_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("SELECT * FROM proderj_links")


async def test_url_fora_do_site_e_recusada_pelo_banco(conn_ingest):
    carga = uuid4()
    await conn_ingest.execute(
        "INSERT INTO cargas (id, fonte, data_referencia, status) "
        "VALUES (%s, 'proderj', current_date, 'em_andamento')",
        (carga,),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        await conn_ingest.execute(
            "INSERT INTO proderj_links VALUES "
            "(%s, '430002/1/2025', 1, 'javascript:alert(1)', 't', 'x')",
            (carga,),
        )
    await conn_ingest.rollback()


async def test_busca_continua_atualizavel_depois_da_migracao(conn_ingest, siga):
    assert await atualizar_busca(conn_ingest) is True
