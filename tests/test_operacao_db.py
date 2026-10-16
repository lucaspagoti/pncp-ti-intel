"""Digest no Postgres descartável: carga inicial, snapshot, falha, reenvio e fuso."""

from datetime import UTC, datetime, timedelta

import httpx
import siga_dados as d

from pncp_ti.fontes.siga import arquivos_de_diretorio, carregar
from pncp_ti.fontes.siga_csv import CABECALHO_ATAS, CABECALHO_ITENS
from pncp_ti.operacao import SP, enfileirar, entregar


async def carga(conn, tmp_path, conjunto, forcar=False):
    pasta = tmp_path / str(len(list(tmp_path.iterdir())))
    pasta.mkdir()
    d.escrever(pasta, conjunto)
    return await carregar(conn, arquivos_de_diretorio(pasta), forcar=forcar)


async def fila(conn):
    return await (
        await conn.execute("SELECT * FROM notificacoes WHERE chave LIKE 'digest:%%' ORDER BY chave")
    ).fetchall()


async def test_carga_inicial_nao_envia_acervo_e_alertas_nao_duplicam(conn_ingest, tmp_path):
    await carga(conn_ingest, tmp_path, d.conjunto_basico())
    agora = datetime.now(SP)
    async with conn_ingest.transaction():
        await enfileirar(conn_ingest, agora)
    assert await fila(conn_ingest) == []
    primeiro = await (await conn_ingest.execute("SELECT count(*) n FROM notificacoes")).fetchone()
    await conn_ingest.commit()
    async with conn_ingest.transaction():
        await enfileirar(conn_ingest, agora)
    segundo = await (await conn_ingest.execute("SELECT count(*) n FROM notificacoes")).fetchone()
    assert primeiro == segundo


async def test_digest_falha_reenvio_reprocessamento_e_nova_troca_snapshot(
    conn_ingest, tmp_path, monkeypatch
):
    monkeypatch.setenv("PNCP_TI_NOTIFY_URL", "http://bridge.invalid/notify/text")
    await carga(conn_ingest, tmp_path, d.conjunto_basico())
    # Simula carga inicial no dia anterior e uma ata conhecida também no dia anterior.
    await conn_ingest.execute("UPDATE cargas SET concluido_em = now() - interval '1 day'")
    await conn_ingest.execute(
        "UPDATE atas_vistas SET primeira_vez_vista = primeira_vez_vista - 1 WHERE id_origem='1'"
    )
    await conn_ingest.commit()
    agora = datetime.now(SP)
    async with conn_ingest.transaction():
        await enfileirar(conn_ingest, agora)
    primeiro = await fila(conn_ingest)
    assert len(primeiro) == 1
    assert "[id 1]" not in primeiro[0]["corpo"]
    assert "[id 4]" in primeiro[0]["corpo"]
    assert "[id 3]" not in primeiro[0]["corpo"]  # interrompida
    assert "[id 5]" not in primeiro[0]["corpo"]  # vencida
    await conn_ingest.commit()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": False}))
    ) as client:
        assert await entregar(conn_ingest, client) >= 1
    assert (await fila(conn_ingest))[0]["enviado_em"] is None
    await conn_ingest.commit()
    await carga(conn_ingest, tmp_path, d.conjunto_basico(), forcar=True)
    async with conn_ingest.transaction():
        await enfileirar(conn_ingest, agora)
    assert len(await fila(conn_ingest)) == 1
    await conn_ingest.commit()

    chamadas = []

    def ok(req):
        chamadas.append(req.content)
        return httpx.Response(200, json={"ok": True})

    # A fila já preparada também é reenviável no dia seguinte.
    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as client:
        assert await entregar(conn_ingest, client) == 0
        quantidade = len(chamadas)
        assert await entregar(conn_ingest, client) == 0
        assert len(chamadas) == quantidade
    enviado = (await fila(conn_ingest))[0]
    assert enviado["enviado_em"] is not None and enviado["tentativas"] == 2
    assert len(enviado["corpo"]) <= 1000


async def test_digest_seleciona_hoje_em_brasilia_mesmo_com_utc_amanha(conn_ingest, tmp_path):
    await carga(conn_ingest, tmp_path, d.conjunto_basico())
    hoje = datetime.now(SP).date()
    await conn_ingest.execute("UPDATE cargas SET concluido_em = now() - interval '1 day'")
    await conn_ingest.commit()
    amanha_utc = datetime.combine(hoje + timedelta(days=1), datetime.min.time(), UTC)
    async with conn_ingest.transaction():
        await enfileirar(conn_ingest, amanha_utc)
    assert str(hoje) in (await fila(conn_ingest))[0]["corpo"]


async def test_enqueue_rollback_nao_marca_atas_como_publicadas(conn_ingest, tmp_path):
    await carga(conn_ingest, tmp_path, d.conjunto_basico())
    await conn_ingest.execute("UPDATE cargas SET concluido_em = now() - interval '1 day'")
    await conn_ingest.commit()
    await enfileirar(conn_ingest, datetime.now(SP))
    assert await fila(conn_ingest)
    await conn_ingest.rollback()
    assert await fila(conn_ingest) == []
    assert not await (await conn_ingest.execute("SELECT 1 FROM digest_atas")).fetchall()


async def test_so_atas_novas_do_snapshot_entram_em_lotes_limitados(conn_ingest, tmp_path):
    await carga(conn_ingest, tmp_path, d.conjunto_basico())
    await conn_ingest.execute("UPDATE cargas SET concluido_em = now() - interval '1 day'")
    await conn_ingest.execute("UPDATE atas_vistas SET primeira_vez_vista = primeira_vez_vista - 1")
    await conn_ingest.commit()
    atas, itens, participantes = d.conjunto_basico()
    extras = range(8, 17)
    novas_atas = d._csv(CABECALHO_ATAS, [d.ata(str(i), "NOTEBOOK " + "A" * 300) for i in extras])
    novos_itens = d._csv(CABECALHO_ITENS, [d.item(str(i), str(i), "NOTEBOOK") for i in extras])
    await carga(
        conn_ingest,
        tmp_path,
        (
            atas + novas_atas.split(b"\r\n", 1)[1],
            itens + novos_itens.split(b"\r\n", 1)[1],
            participantes,
        ),
    )
    async with conn_ingest.transaction():
        await enfileirar(conn_ingest, datetime.now(SP))
    mensagens = await fila(conn_ingest)
    assert len(mensagens) == 3
    assert all(len(m["corpo"]) <= 1000 for m in mensagens)
    assert all("[id 1]" not in m["corpo"] for m in mensagens)
    reservadas = await (await conn_ingest.execute("SELECT identidade FROM digest_atas")).fetchall()
    assert {r["identidade"] for r in reservadas} == {f"siga_rj:{i}" for i in extras}
