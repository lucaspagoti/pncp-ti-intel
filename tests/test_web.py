"""Web local (R4): busca, filtros, detalhe, CSV, cabeçalhos e permissões do `web_reader`."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, timedelta

import httpx
import psycopg
import pytest
import web_dados

from pncp_ti.busca import atualizar_busca
from pncp_ti.config import admin_dsn, get_settings, web_dsn
from pncp_ti.web import consultas
from pncp_ti.web.app import criar_app
from pncp_ti.web.exportar import gerar_csv, neutralizar


def titulos(html: str) -> str:
    """Só o texto dos resultados (o formulário traz exemplos de busca)."""
    return " | ".join(re.findall(r"<h2><a[^>]*>(.*?)</a></h2>", html))


@pytest.fixture
async def dados(conn_ingest):
    for comando, parametros in [*web_dados.comandos(), web_dados.REFRESH]:
        await conn_ingest.execute(comando, parametros)
    await conn_ingest.commit()


async def atualizar(conn_ingest) -> None:
    await conn_ingest.execute(*web_dados.REFRESH)
    await conn_ingest.commit()


@pytest.fixture
async def cliente(nome_banco_teste, dados):
    dsn = web_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    app = criar_app(dsn)
    async with app.router.lifespan_context(app):
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://testserver") as c:
            yield c


async def test_busca_por_objeto_sem_acento_e_por_item(cliente):
    r = await cliente.get("/", params={"q": "impressao"})
    assert r.status_code == 200 and "Outsourcing de impressão" in titulos(r.text)
    assert "notebooks para a rede" not in titulos(r.text)
    r = await cliente.get("/", params={"q": "mouse optico"})  # só existe nos itens
    assert "notebooks para a rede estadual" in titulos(r.text)


async def test_filtros_de_fonte_uf_vencimento_e_preco(cliente):
    assert "Outsourcing" not in titulos((await cliente.get("/", params={"fonte": "siga_rj"})).text)
    r = await cliente.get("/", params={"uf": "SP"})
    assert "licença Microsoft" in titulos(r.text) and "notebooks" not in titulos(r.text)
    r = await cliente.get("/", params={"esfera": "Estadual"})  # SIGA é Estadual/RJ pela view
    assert "notebooks" in titulos(r.text) and "licença Microsoft" not in titulos(r.text)
    # "Vigente até pelo menos": a do dia 5 vence antes; as do dia 60 ficam.
    r = await cliente.get("/", params={"vigente_ate": str(date.today() + timedelta(days=10))})
    assert "licença Microsoft" not in titulos(r.text) and "notebooks" in titulos(r.text)
    r = await cliente.get("/", params={"preco_min": "1.000,00"})  # só o notebook passa
    assert "notebooks" in titulos(r.text) and "Outsourcing" not in titulos(r.text)
    r = await cliente.get("/", params={"preco_max": "0,50"})
    assert "Outsourcing" in titulos(r.text) and "notebooks" not in titulos(r.text)


async def test_texto_de_terceiros_e_escapado(cliente):
    r = await cliente.get("/", params={"q": "microsoft"})
    assert "<script>alert(1)</script>" not in titulos(r.text)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in titulos(r.text)


async def test_parametros_hostis_nao_quebram(cliente):
    for params in (
        {"q": "'; DROP TABLE atas;--"},
        {"orgao": "%_\\"},
        {"ordem": "fim; DROP TABLE atas"},
        {"pagina": "-5"},
        {"pagina": "abc"},
        {"vigente_ate": "ontem"},
        {"esfera": "Não informada"},
        {"preco_min": "1e999999"},
        {"uf": "RJX"},
        {"q": "a" * 5000},
    ):
        assert (await cliente.get("/", params=params)).status_code == 200, params


async def test_htmx_devolve_so_o_bloco(cliente):
    r = await cliente.get("/", headers={"HX-Request": "true"})
    assert "<html" not in r.text and "ata" in r.text


async def test_detalhe_mostra_itens_consumo_e_origem(cliente):
    r = await cliente.get("/ata/siga_rj/S1")
    assert r.status_code == 200
    assert "Notebook 16GB" in r.text and "R$ 4.500,00" in r.text
    assert "SEFAZ" in r.text and "sem link público por ata" not in r.text  # link_origem preenchido
    assert "https://pncp.gov.br/app/atas/1" in r.text
    assert (await cliente.get("/ata/siga_rj/NAOEXISTE")).status_code == 404
    assert (await cliente.get("/ata/fonte_falsa/S1")).status_code == 404


async def test_link_nao_http_nao_vira_href(cliente, conn_ingest):
    await conn_ingest.execute(
        "UPDATE atas SET link_origem = 'javascript:alert(1)' WHERE id_origem='S1'"
    )
    await atualizar(conn_ingest)
    r = await cliente.get("/ata/siga_rj/S1")
    assert "javascript:" not in r.text


async def test_csv_neutraliza_formulas_e_baixa_como_anexo(cliente, conn_ingest):
    await conn_ingest.execute("UPDATE atas SET objeto = '=HYPERLINK(\"x\")' WHERE id_origem='A1'")
    await atualizar(conn_ingest)
    r = await cliente.get("/exportar.csv", params={"fonte": "compras_arp"})
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "'=HYPERLINK" in r.text and ",=HYPERLINK" not in r.text
    assert r.text.splitlines()[0].startswith("fonte,numero,orgao")


def test_neutralizar_e_gerar_csv():
    assert neutralizar("=1+1") == "'=1+1"
    assert neutralizar("  @cmd") == "'  @cmd"
    assert neutralizar("\tx") == "'\tx"
    assert neutralizar(None) == "" and neutralizar("normal") == "normal"
    assert gerar_csv([{"fonte": "x"}]).count("\n") == 2


async def test_cabecalhos_de_seguranca_e_host_invalido(cliente):
    r = await cliente.get("/saude")
    assert r.text == "ok"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert (await cliente.get("/docs")).status_code == 404
    ruim = await cliente.get("/saude", headers={"host": "evil.example"})
    assert ruim.status_code == 400


def test_ler_filtros_normaliza():
    f = consultas.ler_filtros(
        {"fonte": "x", "esfera": "Federal", "uf": "rj", "pagina": "3", "preco_min": "1.234,50"}
    )
    assert (f.fonte, f.esfera, f.uf, f.pagina) == ("", "Federal", "RJ", 3)
    assert str(f.preco_min) == "1234.50"


async def test_web_reader_so_le_views_e_nao_escreve(nome_banco_teste):
    dsn = web_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT count(*) FROM v_busca_atas")
        conn.rollback()
        for comando in (
            "SELECT * FROM atas",
            "SELECT * FROM cargas",
            "SELECT * FROM ata_itens",
            "DELETE FROM atas_vistas",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(comando)
            conn.rollback()


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("12,50", "12.50"),
        ("12.50", "12.50"),
        ("1.000", "1000"),
        ("1.234,50", "1234.50"),
        ("1.234.567", "1234567"),
        ("0,5", "0.5"),
        ("abc", None),
    ],
)
def test_preco_aceita_formatos_e_sobrevive_a_ida_e_volta_pelo_link(texto, esperado):
    f = consultas.ler_filtros({"preco_min": texto})
    assert (None if f.preco_min is None else str(f.preco_min)) == esperado
    if esperado is not None:
        volta = consultas.ler_filtros(f.como_dict())
        assert volta.preco_min == f.preco_min


async def test_faixa_de_preco_exige_um_item_dentro_da_faixa(cliente, conn_ingest):
    # S1 tem itens de R$ 4.500 e R$ 30: a faixa 100–1.000 não tem item dentro, só extremos fora.
    r = await cliente.get("/", params={"preco_min": "100", "preco_max": "1000"})
    assert "notebooks" not in titulos(r.text)
    r = await cliente.get("/", params={"preco_min": "20", "preco_max": "50"})
    assert "notebooks" in titulos(r.text)


async def test_campo_de_preco_do_formulario_sobrevive_a_ida_e_volta(cliente):
    r = await cliente.get("/", params={"preco_max": "0,125", "preco_min": "1.234,50"})
    assert 'name="preco_max" inputmode="decimal" value="0,125"' in r.text
    assert 'name="preco_min" inputmode="decimal" value="1234,50"' in r.text
    r2 = await cliente.get("/", params={"preco_max": "0,125"})
    assert consultas.ler_filtros({"preco_max": "0,125"}).preco_max == consultas.Decimal("0.125")
    assert r2.status_code == 200


async def _leitor(nome_banco_teste):
    dsn = web_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    return await psycopg.AsyncConnection.connect(dsn, autocommit=True)


async def test_facetas_contam_sob_os_outros_filtros(nome_banco_teste, dados):
    conn = await _leitor(nome_banco_teste)
    try:
        todas = await consultas.facetas(conn, consultas.Filtros())
        assert todas["fonte"] == {"siga_rj": 1, "compras_arp": 2}
        assert todas["esfera"] == {"Estadual": 1, "Municipal": 1, "Não informada": 1}
        # A faceta de fonte ignora o próprio filtro de fonte, mas respeita os demais.
        f = consultas.ler_filtros({"fonte": "siga_rj", "esfera": "Municipal"})
        so = await consultas.facetas(conn, f)
        assert so["fonte"] == {"compras_arp": 1} and so["esfera"] == {"Estadual": 1}
        sem = await consultas.buscar(conn, consultas.ler_filtros({"esfera": "Não informada"}))
        assert [a["id_ata"] for a in sem.linhas] == ["A1"]
    finally:
        await conn.close()


def test_filtros_ativos_removem_so_o_proprio_campo():
    f = consultas.ler_filtros(
        {"q": "toner", "uf": "rj", "vigente_ate": "2026-12-31", "pagina": "4"}
    )
    ativos = consultas.filtros_ativos(f)
    assert [(r, v) for r, v, _ in ativos] == [
        ("Termo", "toner"),
        ("UF", "RJ"),
        ("Vigente até pelo menos", "31/12/2026"),
    ]
    sem_uf = ativos[1][2]
    assert (sem_uf.q, sem_uf.uf, sem_uf.pagina) == ("toner", "", 1)


def test_dias_restantes_e_nivel_do_selo():
    hoje = date(2026, 11, 2)
    assert consultas.dias_restantes(date(2026, 11, 15), hoje) == (13, "crit")
    assert consultas.dias_restantes(date(2026, 12, 2), hoje) == (30, "crit")
    assert consultas.dias_restantes(date(2026, 12, 3), hoje) == (31, "warn")
    assert consultas.dias_restantes(date(2027, 1, 31), hoje) == (90, "warn")
    assert consultas.dias_restantes(date(2027, 2, 1), hoje) == (91, "")
    assert consultas.dias_restantes(None, hoje) == (None, "")


async def test_csv_de_itens_da_ata(cliente, conn_ingest):
    await conn_ingest.execute("UPDATE ata_itens SET descricao = '@SUM(1)' WHERE chave = 'S1-2'")
    await atualizar(conn_ingest)
    r = await cliente.get("/ata/siga_rj/S1/itens.csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    linhas = r.text.splitlines()
    assert linhas[0].startswith("id_item,descricao") and len(linhas) == 3
    assert "'@SUM(1)" in r.text and "Notebook 16GB" in r.text
    assert (await cliente.get("/ata/siga_rj/NAOEXISTE/itens.csv")).status_code == 404


async def test_busca_so_muda_depois_do_refresh(cliente, conn_ingest):
    carga = (await (await conn_ingest.execute("SELECT id FROM cargas LIMIT 1")).fetchone())["id"]
    await conn_ingest.execute(*web_dados.ata(carga, "N1", "Aquisição de tablets"))
    await conn_ingest.commit()
    assert "tablets" not in titulos((await cliente.get("/", params={"q": "tablets"})).text)
    await atualizar(conn_ingest)
    assert "tablets" in titulos((await cliente.get("/", params={"q": "tablets"})).text)


async def test_conexao_morta_e_descartada_pelo_pool(cliente, nome_banco_teste):
    assert (await cliente.get("/", params={"q": "toner"})).status_code == 200
    admin = admin_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    with psycopg.connect(admin, autocommit=True) as conn:
        mortas = conn.execute(
            "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity "
            "WHERE usename = 'web_reader' AND datname = %s",
            (nome_banco_teste,),
        ).fetchone()[0]
    assert mortas >= 1
    for _ in range(3):  # antes, a primeira requisição depois do restart dava 500
        assert (await cliente.get("/", params={"q": "impressao"})).status_code == 200
    assert (await cliente.get("/saude")).text == "ok"


async def test_saude_responde_503_sem_banco():
    app = criar_app("host=127.0.0.1 port=1 dbname=nada user=nada connect_timeout=1")
    async with app.router.lifespan_context(app):
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://testserver") as c:
            r = await c.get("/saude")
    assert r.status_code == 503


async def test_web_reader_nao_le_a_mv_nem_dispara_refresh(nome_banco_teste):
    conn = await _leitor(nome_banco_teste)
    try:
        await conn.execute("SELECT count(*) FROM v_cargas_web")
        for comando in ("SELECT * FROM mv_busca_atas", "SELECT atualizar_busca()"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await conn.execute(comando)
    finally:
        await conn.close()


async def test_refresh_que_falha_devolve_false(nome_banco_teste):
    conn = await _leitor(nome_banco_teste)
    try:
        assert await atualizar_busca(conn) is False
    finally:
        await conn.close()
