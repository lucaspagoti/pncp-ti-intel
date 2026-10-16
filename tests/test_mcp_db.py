"""MCP sobre Postgres real descartável; nenhuma credencial ou SQL do cliente."""

from dataclasses import replace

import siga_dados as d

from pncp_ti import mcp_server as server
from pncp_ti.config import get_settings
from pncp_ti.fontes.siga import arquivos_de_diretorio, carregar


async def test_busca_sem_fonte_itens_consumo_e_payload_sql(
    conn_ingest, nome_banco_teste, tmp_path, monkeypatch
):
    d.escrever(tmp_path, d.conjunto_basico())
    await carregar(conn_ingest, arquivos_de_diretorio(tmp_path))
    settings = replace(get_settings(), postgres_db=nome_banco_teste)
    monkeypatch.setattr(server, "get_settings", lambda: settings)
    # '%' permanece literal e não pode virar um wildcard ou SQL fornecido pelo cliente.
    assert await server.buscar_atas("'; DROP TABLE atas; --") == []
    assert await server.buscar_atas("%") == []
    assert {r["id_ata"] for r in await server.buscar_atas("notebook")} == {"4"}
    linhas = await server.consultar(
        server.BUSCAR, dict(fonte=None, termo="%", limite=100, offset=0)
    )
    assert {r["id_ata"] for r in linhas} == {"1", "4", "6", "7"}
    assert await server.itens_ata("siga_rj", "1")
    assert await server.consumo_ata("siga_rj", "1")
    assert await server.itens_ata("compras_arp", "1") == []
