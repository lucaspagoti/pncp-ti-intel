"""Fila de notificações no Postgres descartável: só alertas de incidente (ADR 0027)."""

from datetime import datetime

import httpx
import siga_dados as d

from pncp_ti.fontes.siga import arquivos_de_diretorio, carregar
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


async def test_atas_novas_nao_geram_digest_e_pendente_antigo_nao_sai(
    conn_ingest, tmp_path, monkeypatch
):
    # WhatsApp só para incidentes (ADR 0027): nem digest novo nem digest legado na fila.
    monkeypatch.setenv("PNCP_TI_NOTIFY_URL", "http://bridge.invalid/notify/text")
    await carga(conn_ingest, tmp_path, d.conjunto_basico())
    await conn_ingest.execute("UPDATE cargas SET concluido_em = now() - interval '1 day'")
    await conn_ingest.execute(
        "INSERT INTO notificacoes (chave, corpo) VALUES ('digest:legado', 'Novas atas de TI')"
    )
    await conn_ingest.commit()
    async with conn_ingest.transaction():
        await enfileirar(conn_ingest, datetime.now(SP))
    assert [m["chave"] for m in await fila(conn_ingest)] == ["digest:legado"]
    assert not await (await conn_ingest.execute("SELECT 1 FROM digest_atas")).fetchall()
    # Só o SIGA foi carregado: a ausência do ARP é um incidente e precisa sair.
    chave_alerta = f"alerta:{datetime.now(SP).date()}:compras_arp:ausente"

    chamadas = []

    def ok(req):
        chamadas.append(req.content.decode())
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as client:
        assert await entregar(conn_ingest, client) == 0
    assert "compras_arp: nenhuma carga ativa." in chamadas
    assert all("Novas atas" not in c for c in chamadas)
    alerta = await (
        await conn_ingest.execute("SELECT * FROM notificacoes WHERE chave = %s", (chave_alerta,))
    ).fetchone()
    assert alerta["enviado_em"] is not None and alerta["tentativas"] == 1
    legado = (await fila(conn_ingest))[0]
    assert legado["enviado_em"] is None and legado["tentativas"] == 0
