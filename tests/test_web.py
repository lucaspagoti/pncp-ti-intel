"""Web local (R4, W2): busca, filtros, detalhe, CSV, cabeçalhos e permissões do `web_reader`."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, timedelta
from uuid import uuid4

import httpx
import psycopg
import pytest
import web_dados

from pncp_ti.busca import atualizar_busca
from pncp_ti.config import admin_dsn, get_settings, web_dsn
from pncp_ti.fontes import proderj as proderj_mod
from pncp_ti.web import consultas
from pncp_ti.web.app import criar_app
from pncp_ti.web.exportar import gerar_csv, neutralizar


def titulos(html: str) -> str:
    """Só o texto dos cartões de resultado."""
    return " | ".join(re.findall(r'<h2 class="ata-objeto"><a [^>]*>(.*?)</a>', html))


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
    r = await cliente.get("/", params={"vigente_ate": str(web_dados.HOJE + timedelta(days=10))})
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


async def test_htmx_devolve_so_a_casca(cliente):
    r = await cliente.get("/", params={"q": "notebook"}, headers={"HX-Request": "true"})
    assert "<html" not in r.text and "<form" not in r.text
    assert r.text.lstrip().startswith("<aside") and "notebooks para a rede" in titulos(r.text)
    # A restauração do histórico (voltar do navegador) precisa da página inteira.
    cab = {"HX-Request": "true", "HX-History-Restore-Request": "true"}
    assert "<html" in (await cliente.get("/", headers=cab)).text
    assert '<div class="casca" id="casca">' in (await cliente.get("/", params={"q": "a"})).text


async def test_detalhe_mostra_itens_e_origem(cliente):
    r = await cliente.get("/ata/siga_rj/S1")
    assert r.status_code == 200
    assert "Notebook 16GB" in r.text and "R$ 4.500,00" in r.text
    assert 'href="https://pncp.gov.br/app/atas/1"' in r.text and "Conferir no portal" in r.text
    assert 'href="/ata/siga_rj/S1/itens.csv"' in r.text
    # Fora do MVP (ADR 0033): o detalhe não mostra mais demandado × consumido.
    assert "SEFAZ" not in r.text
    assert (await cliente.get("/ata/siga_rj/NAOEXISTE")).status_code == 404
    assert (await cliente.get("/ata/fonte_falsa/S1")).status_code == 404


async def test_link_nao_http_nao_vira_href(cliente, conn_ingest):
    await conn_ingest.execute(
        "UPDATE atas SET link_origem = 'javascript:alert(1)' WHERE id_origem='S1'"
    )
    await atualizar(conn_ingest)
    r = await cliente.get("/ata/siga_rj/S1")
    assert "javascript:" not in r.text and "Conferir no portal" not in r.text


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


async def test_csv_de_itens_nao_corta_em_2000(cliente, conn_ingest):
    """QA-003: a tela corta em 2.000 itens; a exportação leva todos."""
    carga = (
        await (
            await conn_ingest.execute("SELECT id FROM cargas WHERE fonte = 'compras_arp'")
        ).fetchone()
    )["id"]
    linhas = [web_dados.item(carga, "A1", n, f"Item {n}", 1) for n in range(2, 2002)]
    async with conn_ingest.cursor() as cur:
        await cur.executemany(linhas[0][0], [parametros for _, parametros in linhas])
    await atualizar(conn_ingest)
    r = await cliente.get("/ata/compras_arp/A1/itens.csv")
    assert len(r.text.splitlines()) == 1 + 2001


RAIZ_WEB = consultas.__file__.rsplit("/", 1)[0]


def test_templates_e_css_sem_estilo_inline_nem_cor_fora_dos_tokens():
    """CSP `style-src 'self'` e design system: nada de `style=` e hex só no tokens.css gerado."""
    from pathlib import Path

    web = Path(RAIZ_WEB)
    for modelo in (web / "templates").glob("*.html"):
        texto = modelo.read_text(encoding="utf-8")
        assert not re.search(r"\bstyle\s*=|<style", texto, re.I), modelo.name
    css = (web / "static" / "app.css").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert not re.search(r"\brgba?\(", css)
    # Tamanho de fonte só pela escala do tokens.css, nunca um valor avulso.
    assert not re.findall(r"font-size:\s*[^v\s]", css)
    assert not (web / "static" / "estilo.css").exists()
    assert not (web / "static" / "tokens-projeto.css").exists()


async def test_inter_e_servida_pela_propria_web_e_a_csp_deixa(cliente):
    """ADR 0040: a fonte vem de /static (`font-src 'self'`), com a licença ao lado."""
    r = await cliente.get("/static/fonts/inter-latin-wght-normal.woff2")
    assert r.status_code == 200 and r.headers["content-type"] == "font/woff2"
    assert r.content[:4] == b"wOF2" and 20_000 < len(r.content) < 200_000
    assert "font-src 'self'" in r.headers["content-security-policy"]
    assert "style-src 'self'" in r.headers["content-security-policy"]  # e segue sem unsafe-inline
    assert "SIL Open Font License" in (await cliente.get("/static/fonts/OFL-Inter.txt")).text
    r = await cliente.get("/")
    assert 'rel="preload" href="/static/fonts/inter-latin-wght-normal.woff2"' in r.text


async def test_botao_de_busca_dentro_do_campo_na_home_e_na_lista(cliente):
    for params in ({}, {"q": "notebook"}):
        r = await cliente.get("/", params=params)
        assert re.search(
            r'<div class="campo-busca">.*?<input type="search".*?'
            r'<button class="busca-botao" type="submit" aria-label="Buscar">',
            r.text,
            re.S,
        ), params
        assert '<button class="botao" type="submit">Buscar' not in r.text
    assert "Experimente" not in (await cliente.get("/")).text


async def test_nome_e_icone_do_portal_em_todas_as_telas(cliente):
    """ADR 0041: o nome no título da aba, na marca e na home, e o ícone da aba ligado."""
    paginas = {
        "/": "<title>Portal de Atas de TI</title>",
        "/?q=notebook": "<title>notebook · Portal de Atas de TI</title>",
        "/?explorar=1": "<title>Portal de Atas de TI</title>",
        "/ata/siga_rj/S1": "· Portal de Atas de TI</title>",
    }
    for url, titulo in paginas.items():
        r = await cliente.get(url)
        assert titulo in r.text, url
        assert '<link rel="icon" href="/static/icone.svg" type="image/svg+xml">' in r.text
        assert (
            '<link rel="icon" href="/static/icone-32.png" type="image/png" sizes="32x32">' in r.text
        )
        assert '<link rel="apple-touch-icon" href="/static/icone-apple-180.png">' in r.text
        assert "Atas de TI vigentes</title>" not in r.text
    lista = (await cliente.get("/", params={"q": "notebook"})).text
    assert re.search(
        r'<a class="marca" href="/"><span class="selo" aria-hidden="true">.*?</span>'
        r"Portal de Atas de TI</a>",
        lista,
        re.S,
    )
    home = (await cliente.get("/")).text
    assert 'class="selo selo-grande"' in home and "<h1>Portal de Atas de TI</h1>" in home


async def test_arquivos_do_icone_sao_servidos_com_o_tipo_certo(cliente):
    esperado = {
        "icone.svg": "image/svg+xml",
        "icone-32.png": "image/png",
        "icone-192.png": "image/png",
        "icone-apple-180.png": "image/png",
    }
    for nome, tipo in esperado.items():
        r = await cliente.get(f"/static/{nome}")
        assert r.status_code == 200 and r.headers["content-type"].startswith(tipo), nome
    assert (await cliente.get("/static/icone-32.png")).content[:8] == b"\x89PNG\r\n\x1a\n"
    svg = (await cliente.get("/static/icone.svg")).text
    assert "<script" not in svg and "http" not in svg.replace("http://www.w3.org/2000/svg", "")


async def test_resposta_parcial_do_htmx_leva_o_titulo_da_aba(cliente):
    """QA-W8-001: o HTMX troca só a casca; o título novo vem na resposta e vale uma vez só."""
    cab = {"HX-Request": "true"}
    r = await cliente.get("/", params={"q": "notebook"}, headers=cab)
    assert r.text.count("<title>") == 1
    assert "<title>notebook · Portal de Atas de TI</title>" in r.text
    r = await cliente.get("/", headers=cab)  # sem termo: todas as atas
    assert "<title>Portal de Atas de TI</title>" in r.text
    r = await cliente.get("/", params={"q": "<script>x</script>"}, headers=cab)
    assert "<title>&lt;script&gt;x&lt;/script&gt; · Portal de Atas de TI</title>" in r.text
    # A página inteira tem um título só (o do base.html), inclusive na restauração do histórico.
    cheia = {**cab, "HX-History-Restore-Request": "true"}
    for cabecalhos in ({}, cheia):
        r = await cliente.get("/", params={"q": "notebook"}, headers=cabecalhos)
        assert r.text.count("<title>") == 1, cabecalhos


async def test_detalhe_tem_a_marca_do_portal(cliente):
    """QA-W8-002: o detalhe não tem lateral, então a marca vem no topo."""
    r = await cliente.get("/ata/siga_rj/S1")
    assert re.search(
        r'<div class="detalhe-marca"><a class="marca" href="/">'
        r'<span class="selo" aria-hidden="true">.*?</span>Portal de Atas de TI</a></div>',
        r.text,
        re.S,
    )


def test_tokens_da_web_sao_os_do_prototipo():
    """O protótipo é a referência visual (ADR 0033): os dois carregam o mesmo tokens.css."""
    from pathlib import Path

    web = Path(RAIZ_WEB) / "static" / "tokens.css"
    prototipo = Path(RAIZ_WEB).parents[2] / "prototipos" / "web" / "tokens.css"
    assert web.read_bytes() == prototipo.read_bytes()


async def test_paginas_sem_estilo_inline(cliente):
    for url in ("/", "/?explorar=1", "/?q=notebook", "/ata/siga_rj/S1", "/ata/compras_arp/A2"):
        assert not re.search(r"\bstyle\s*=", (await cliente.get(url)).text), url


async def test_lateral_mostra_facetas_e_marca_a_opcao(cliente):
    r = await cliente.get("/", params={"fonte": "siga_rj"})
    assert re.search(r'value="siga_rj" checked> SIGA RJ</span><span class="qtd">1<', r.text)
    assert re.search(r'value="compras_arp" > Compras ARP</span><span class="qtd">2<', r.text)
    assert "PNCP</span>" not in r.text  # sem atas da busca PNCP: a opção não aparece
    # A opção escolhida aparece mesmo quando os outros filtros zeram a contagem dela.
    r = await cliente.get("/", params={"esfera": "Municipal", "uf": "RJ"})
    assert re.search(r'value="Municipal" checked> Municipal</span><span class="qtd">0<', r.text)
    assert "Nenhuma ata encontrada para esses filtros." in r.text


async def test_pilulas_e_selo_de_vencimento(cliente):
    r = await cliente.get("/", params={"q": "microsoft", "uf": "SP"})
    assert 'aria-label="Remover termo"' in r.text and 'aria-label="Remover uf"' in r.text
    assert 'href="/?uf=SP"' in r.text  # remover o termo mantém a UF
    assert '<p class="prazo crit">vence em 5 dias</p>' in r.text
    r = await cliente.get("/", params={"q": "notebook"})
    assert '<p class="prazo warn">vence em 60 dias</p>' in r.text
    assert "<h1>1 ata vigente</h1>" in r.text


async def test_ata_sem_itens_e_rodape_com_a_data_da_carga(cliente):
    r = await cliente.get("/", params={"q": "microsoft"})
    assert "sem itens nesta fonte" in r.text
    assert f"Dados de <strong>{web_dados.HOJE:%d/%m/%Y}</strong>" in r.text
    r = await cliente.get("/ata/compras_arp/A2")
    assert "Esta fonte não traz itens para esta ata." in r.text and "itens.csv" not in r.text
    assert "Municipal · SP" in r.text
    fim = web_dados.HOJE + timedelta(days=5)
    assert f"até {fim:%d/%m/%Y}" in r.text  # sem início


async def test_paginacao_de_20_em_20(cliente, conn_ingest):
    carga = (
        await (
            await conn_ingest.execute("SELECT id FROM cargas WHERE fonte = 'compras_arp'")
        ).fetchone()
    )["id"]
    for n in range(25):
        await conn_ingest.execute(*web_dados.ata(carga, f"L{n}", f"Cabo lote {n}"))
    await atualizar(conn_ingest)
    r = await cliente.get("/", params={"q": "cabo"})
    assert "<h1>25 atas vigentes</h1>" in r.text and "página 1 de 2" in r.text
    assert '<span class="seta" aria-disabled="true">Anterior</span>' in r.text
    assert '<span aria-current="page">1</span>' in r.text and 'aria-label="Página 2"' in r.text
    r = await cliente.get("/", params={"q": "cabo", "pagina": "2"})
    assert "página 2 de 2" in r.text and len(titulos(r.text).split(" | ")) == 5
    assert '<span class="seta" aria-disabled="true">Próxima</span>' in r.text


async def test_descricao_longa_vira_resumo_com_especificacao(cliente, conn_ingest):
    longa = "Notebook " + "especificação detalhada " * 20
    await conn_ingest.execute("UPDATE ata_itens SET descricao = %s WHERE chave = 'S1-1'", (longa,))
    await atualizar(conn_ingest)
    r = await cliente.get("/ata/siga_rj/S1")
    assert '<span class="ver">Ver especificação completa</span>' in r.text
    assert r.text.count(longa.strip()) == 2  # no <details> (tela) e no bloco de impressão
    assert "Mouse óptico</td>" in r.text or "Mouse óptico<span" in r.text  # curta fica inteira


async def _semear_monitores(conn_ingest):
    """O caso do Lucas (02/11/2026): "monitor" trazia primeiro uma ata de CFTV."""
    arp = (
        await (
            await conn_ingest.execute("SELECT id FROM cargas WHERE fonte = 'compras_arp'")
        ).fetchone()
    )["id"]
    cftv = [
        web_dados.item(
            arp,
            "CFTV",
            n,
            f"CÂMERA DIGITAL, videomonitoramento {n}",
            900,
            catalogo="CÂMERA DIGITAL",
        )
        for n in range(1, 12)
    ]
    cftv.append(
        web_dados.item(
            arp, "CFTV", 12, "MONITOR IMAGEM, TAMANHO TELA 55 POL", 4000, catalogo="MONITOR IMAGEM"
        )
    )
    comandos = [
        web_dados.ata(
            arp,
            "CFTV",
            "Solução de videomonitoramento com monitoramento remoto e controle de acesso",
        ),
        *cftv,
        web_dados.ata(arp, "CFTV2", "Videomonitoramento e monitoramento de imagens"),
        web_dados.item(
            arp, "CFTV2", 1, "CÂMERA DIGITAL, videomonitoramento", 900, catalogo="CÂMERA DIGITAL"
        ),
        web_dados.ata(arp, "MON", "Aquisição de equipamentos de informática"),
        web_dados.item(
            arp,
            "MON",
            1,
            "MONITOR COMPUTADOR, TAMANHO TELA 23 A 30 POL",
            618,
            catalogo="MONITOR COMPUTADOR",
        ),
        web_dados.item(
            arp,
            "MON",
            2,
            "MONITOR COMPUTADOR, TAMANHO TELA 31 A 40 POL",
            3230,
            catalogo="MONITOR COMPUTADOR",
        ),
        web_dados.ata(arp, "PC", "Registro de preços de computadores"),
        web_dados.item(
            arp,
            "PC",
            1,
            "MICROCOMPUTADOR, MEMÓRIA 16 GB, com monitor 24 pol",
            4500,
            catalogo="MICROCOMPUTADOR",
        ),
        web_dados.item(arp, "PC", 2, "TECLADO, ABNT2", 60, catalogo="TECLADO"),
    ]
    for comando, parametros in comandos:
        await conn_ingest.execute(comando, parametros)
    await atualizar(conn_ingest)


async def test_monitor_traz_primeiro_a_ata_cujo_item_principal_e_monitor(cliente, conn_ingest):
    await _semear_monitores(conn_ingest)
    r = await cliente.get("/", params={"q": "monitor"})
    ordem = re.findall(r'href="/ata/compras_arp/(\w+)"', r.text)
    # Ata de monitores; CFTV com um item que é monitor; computador que cita monitor na
    # especificação; e por último o CFTV que só casa pelo radical de "monitoramento".
    assert ordem == ["MON", "CFTV", "PC", "CFTV2"], ordem
    # A linha mostra o item que casou e o preço dele, não o menor preço da ata.
    assert "<mark>Monitor</mark> computador" in r.text and "2 de 2 itens" in r.text
    assert '<span class="moeda">R$</span>618,00' in r.text and "do item buscado" in r.text
    # "monitores" (plural) dá a mesma ordem; o radical de "monitoramento" não puxa o CFTV para cima.
    plural = re.findall(
        r'href="/ata/compras_arp/(\w+)"', (await cliente.get("/", params={"q": "monitores"})).text
    )
    assert plural[0] == "MON"


async def test_preco_filtrado_pelo_item_buscado(cliente, conn_ingest):
    await _semear_monitores(conn_ingest)
    # O teclado de R$ 60 não faz a ata de computadores passar numa faixa de monitor barato.
    r = await cliente.get("/", params={"q": "monitor", "preco_max": "100"})
    assert "/ata/compras_arp/PC" not in r.text
    r = await cliente.get("/", params={"q": "monitor", "preco_max": "700"})
    assert "/ata/compras_arp/MON" in r.text


async def test_sinonimo_amplia_a_busca(cliente, conn_ingest):
    carga = (
        await (
            await conn_ingest.execute("SELECT id FROM cargas WHERE fonte = 'compras_arp'")
        ).fetchone()
    )["id"]
    await conn_ingest.execute(*web_dados.ata(carga, "LAP", "Aquisição de computador portátil"))
    await atualizar(conn_ingest)
    r = await cliente.get("/", params={"q": "notebook"})
    assert "/ata/compras_arp/LAP" in r.text and "/ata/siga_rj/S1" in r.text


async def test_voce_quis_dizer_com_zero_resultados(cliente, conn_ingest):
    await _semear_monitores(conn_ingest)
    r = await cliente.get("/", params={"q": "monitr"})
    assert "Nenhuma ata encontrada" in r.text and "Você quis dizer" in r.text
    assert 'href="/?q=monitor"' in r.text


async def test_item_buscado_sem_preco_nao_herda_preco_de_outro_item(cliente, conn_ingest):
    """W3-R0-001: o monitor sem preço válido não vira o teclado de R$ 25."""
    carga = (
        await (
            await conn_ingest.execute("SELECT id FROM cargas WHERE fonte = 'compras_arp'")
        ).fetchone()
    )["id"]
    for comando, parametros in (
        web_dados.ata(carga, "SP", "Aquisição de periféricos"),
        web_dados.item(
            carga, "SP", 1, "MONITOR COMPUTADOR, 24 POL", None, catalogo="MONITOR COMPUTADOR"
        ),
        web_dados.item(carga, "SP", 2, "TECLADO, ABNT2", 25, catalogo="TECLADO"),
    ):
        await conn_ingest.execute(comando, parametros)
    await conn_ingest.execute("UPDATE ata_itens SET valor_valido = false WHERE chave = 'SP-1'")
    await atualizar(conn_ingest)
    r = await cliente.get("/", params={"q": "monitor"})
    linha = r.text[r.text.index('href="/ata/compras_arp/SP"') :].split("</li>", 1)[0]
    assert "25,00" not in linha and "sem preço do item buscado" in linha
    r = await cliente.get("/", params={"q": "monitor", "preco_max": "100"})
    assert "/ata/compras_arp/SP" not in r.text


async def test_frase_negada_nao_perde_ata_na_fronteira_entre_campos(cliente, conn_ingest):
    """W3-R0-002: o vetor de recuperação é o da 0010; juntar objeto e cabeça criaria a frase
    "notebook monitor" e a busca negada perderia a ata."""
    carga = (
        await (
            await conn_ingest.execute("SELECT id FROM cargas WHERE fonte = 'compras_arp'")
        ).fetchone()
    )["id"]
    await conn_ingest.execute(*web_dados.ata(carga, "NEG", "Notebook"))
    await conn_ingest.execute(*web_dados.item(carga, "NEG", 1, "Monitor", 500, catalogo="MONITOR"))
    await atualizar(conn_ingest)
    r = await cliente.get("/", params={"q": 'notebook -"notebook monitor"'})
    assert "/ata/compras_arp/NEG" in r.text


async def test_sem_parametro_a_primeira_visita_e_a_home(cliente):
    r = await cliente.get("/")
    assert "<h1>Portal de Atas de TI</h1>" in r.text and 'name="q"' in r.text
    # Só o que o leitor precisa para começar: sem lista, sem filtros.
    assert 'class="lista-atas' not in r.text and 'id="casca"' not in r.text
    assert 'href="/?q=notebook"' in r.text and 'href="/?explorar=1"' in r.text
    assert f"Dados de <strong>{web_dados.HOJE:%d/%m/%Y}</strong>" in r.text
    assert re.search(r"em [\d.]+ atas vigentes", r.text)
    # Campo vazio enviado pelo formulário da home também volta para a home.
    assert "<h1>Portal de Atas de TI</h1>" in (await cliente.get("/", params={"q": ""})).text


async def test_explorar_lista_todas_as_atas(cliente):
    r = await cliente.get("/", params={"explorar": "1"})
    assert 'class="lista-atas' in r.text and 'id="casca"' in r.text
    assert (
        "<h1>Portal de Atas de TI</h1>" not in r.text
        and 'aria-label="Filtros ativos"' not in r.text
    )
    # Ordem escolhida sem filtro é lista, não home.
    assert 'class="lista-atas' in (await cliente.get("/", params={"ordem": "preco"})).text


async def test_ultimo_filtro_removido_pelo_htmx_guarda_explorar_na_url(cliente):
    cab = {"HX-Request": "true"}
    r = await cliente.get("/", headers=cab)
    assert r.headers["HX-Push-Url"] == "/?explorar=1" and 'class="lista-atas' in r.text
    # Com filtro (inclusive o `ordem` que o formulário sempre manda) a URL é a do pedido.
    r = await cliente.get("/", params={"ordem": "relevancia"}, headers=cab)
    assert "HX-Push-Url" not in r.headers
    # O link da última pílula já aponta para a lista inteira, e não para a home.
    r = await cliente.get("/", params={"q": "notebook"})
    assert 'href="/?explorar=1"' in r.text and 'hx-get="/?explorar=1"' in r.text


def test_janela_de_paginas():
    janela = consultas.janela_paginas
    assert janela(1, 1) == [1] and janela(1, 3) == [1, 2, 3]
    assert janela(1, 10) == [1, 2, None, 10]
    assert janela(5, 10) == [1, None, 4, 5, 6, None, 10]
    assert janela(3, 10) == [1, 2, 3, 4, None, 10]  # a lacuna de uma página vira o número
    assert janela(10, 10) == [1, None, 9, 10]
    assert janela(500, 500) == [1, None, 499, 500]


# --- PRODERJ: abas "Todas | PRODERJ" e botão da contratação (ADR 0042) ---------------------------


@pytest.fixture
async def proderj(conn_ingest, dados):
    """Duas atas do PRODERJ no SIGA: uma com página no site, outra que não consta."""
    siga = (
        await (
            await conn_ingest.execute("SELECT id FROM cargas WHERE fonte = 'siga_rj' AND ativa")
        ).fetchone()
    )["id"]
    comandos = [
        web_dados.ata_proderj(siga, "P1", "MICROSOFT", "SEI-430002/000030/2024"),
        web_dados.ata_proderj(siga, "P2", "OUTSOURCING DE IMPRESSÃO", "SEI-430002/009999/2025"),
        web_dados.REFRESH,
    ]
    for comando, parametros in comandos:
        await conn_ingest.execute(comando, parametros)
    elo = proderj_mod.Link(
        "430002/30/2024", 1779, proderj_mod.URL_NODE.format(1779), "PE-RP 012/2025", "homologadas"
    )
    await proderj_mod.publicar(conn_ingest, {elo.processo: elo}, 1, uuid4())
    await conn_ingest.commit()


async def test_aba_proderj_lista_so_as_atas_do_orgao(cliente, proderj):
    r = await cliente.get("/", params={"escopo": "proderj"})
    assert titulos(r.text) in {
        "MICROSOFT | OUTSOURCING DE IMPRESSÃO",
        "OUTSOURCING DE IMPRESSÃO | MICROSOFT",
    }
    assert "2 atas vigentes" in r.text
    assert re.search(r'id="escopo-proderj"[^>]*checked', r.text)
    assert "pilula" not in r.text  # a aba já diz o escopo; não vira pílula de filtro


async def test_abas_trazem_as_duas_contagens_sob_os_demais_filtros(cliente, proderj):
    r = await cliente.get("/", params={"explorar": "1"})
    assert re.search(r"Todas as atas <span class=\"qtd\">5</span>", r.text)
    assert re.search(r"PRODERJ <span class=\"qtd\">2</span>", r.text)
    r = await cliente.get("/", params={"q": "microsoft"})
    assert re.search(r"PRODERJ <span class=\"qtd\">1</span>", r.text)


async def test_sem_atas_do_proderj_nao_ha_aba(cliente):
    r = await cliente.get("/", params={"explorar": "1"})
    assert r.status_code == 200 and 'id="escopo-proderj"' not in r.text


async def test_escopo_desconhecido_e_ignorado(cliente, proderj):
    r = await cliente.get("/", params={"escopo": "outro"})
    assert "5 atas vigentes" in r.text and not re.search(r'id="escopo-proderj"[^>]*checked', r.text)


async def test_escopo_fica_na_exportacao_csv(cliente, proderj):
    r = await cliente.get("/exportar.csv", params={"escopo": "proderj"})
    assert (
        "MICROSOFT" in r.text
        and "notebooks" not in r.text
        and "Outsourcing de impressão" not in r.text
    )


async def test_detalhe_com_pagina_leva_ao_site_do_proderj(cliente, proderj):
    r = await cliente.get("/ata/siga_rj/P1")
    assert 'href="https://www.rj.gov.br/proderj/node/1779"' in r.text
    assert "Ver no site do PRODERJ" in r.text and "aria-disabled" not in r.text
    assert 'rel="noopener noreferrer"' in r.text


async def test_detalhe_sem_pagina_mostra_o_botao_desativado(cliente, proderj):
    r = await cliente.get("/ata/siga_rj/P2")
    assert 'aria-disabled="true"' in r.text and "Não consta no site do PRODERJ" in r.text
    assert "Ver no site do PRODERJ" not in r.text and "rj.gov.br" not in r.text.replace(
        "rj.gov.br/proderj/licitacoes", ""
    )


async def test_detalhe_de_outro_orgao_nao_tem_botao_do_proderj(cliente, proderj):
    r = await cliente.get("/ata/siga_rj/S1")
    assert r.status_code == 200 and "PRODERJ" not in r.text


def test_url_do_proderj_so_aceita_o_proprio_site():
    from pncp_ti.web.app import _url_proderj

    assert _url_proderj("https://www.rj.gov.br/proderj/node/1779")
    for ruim in (
        None,
        "",
        "javascript:alert(1)",
        "https://evil.example/proderj/node/1",
        "http://www.rj.gov.br/proderj/node/1",
        "https://www.rj.gov.br/outro/node/1",
    ):
        assert _url_proderj(ruim) == ""
