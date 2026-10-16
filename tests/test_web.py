"""Web local (R4): busca, filtros, detalhe, CSV, cabeçalhos e permissões do `web_reader`."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, timedelta
from uuid import uuid4

import httpx
import psycopg
import pytest

from pncp_ti.config import get_settings, web_dsn
from pncp_ti.web import consultas
from pncp_ti.web.app import criar_app
from pncp_ti.web.exportar import gerar_csv, neutralizar


def titulos(html: str) -> str:
    """Só o texto dos resultados (o formulário traz exemplos de busca)."""
    return " | ".join(re.findall(r"<h2><a[^>]*>(.*?)</a></h2>", html))


FIM = date.today() + timedelta(days=60)


async def _ata(conn, carga, fonte_id, objeto, *, fim=FIM, orgao="ORGAO X", uf=None, esfera=None):
    await conn.execute(
        "INSERT INTO atas (carga_id, id_origem, numero, objeto, orgao, status_origem, is_ti, "
        "vigente_na_origem, fim, uf, esfera, link_origem) "
        "VALUES (%s, %s, '1/2026', %s, %s, 'Válida', true, true, %s, %s, %s, %s)",
        (carga, fonte_id, objeto, orgao, fim, uf, esfera, "https://pncp.gov.br/app/atas/1"),
    )


async def _item(conn, carga, ata, n, descricao, valor, fornecedor="ACME"):
    await conn.execute(
        "INSERT INTO ata_itens (carga_id, chave, ata_id_origem, id_item, descricao, nome_catalogo, "
        "fornecedor, quantidade, valor_unitario, valor_valido) "
        "VALUES (%s, %s, %s, %s, %s, '', %s, 10, %s, true)",
        (carga, f"{ata}-{n}", ata, str(n), descricao, fornecedor, valor),
    )


@pytest.fixture
async def dados(conn_ingest):
    siga, arp = uuid4(), uuid4()
    for carga, fonte in ((siga, "siga_rj"), (arp, "compras_arp")):
        await conn_ingest.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
            "VALUES (%s, %s, %s, 'concluida', true)",
            (carga, fonte, date.today()),
        )
    await _ata(conn_ingest, siga, "S1", "Aquisição de notebooks para a rede estadual")
    await _item(conn_ingest, siga, "S1", 1, "Notebook 16GB", 4500)
    await _item(conn_ingest, siga, "S1", 2, "Mouse óptico", 30)
    await _ata(conn_ingest, arp, "A1", "Outsourcing de impressão departamental", orgao="MINISTERIO")
    await _item(conn_ingest, arp, "A1", 1, "Impressão A4 monocromática", 0.12)
    await _ata(
        conn_ingest,
        arp,
        "A2",
        "<script>alert(1)</script> licença Microsoft",
        fim=date.today() + timedelta(days=5),
        uf="SP",
        esfera="Municipal",
    )
    await conn_ingest.execute(
        "INSERT INTO ata_participantes (carga_id, chave, ata_id_origem, id_item, item, unidade, "
        "qtd_demandada, qtd_consumida) VALUES (%s, 'p1', 'S1', '1', 'Notebook', 'SEFAZ', 5, 2)",
        (siga,),
    )
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
    r = await cliente.get("/", params={"vence_ate": str(date.today() + timedelta(days=10))})
    assert "licença Microsoft" in titulos(r.text) and "notebooks" not in titulos(r.text)
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
        {"vence_ate": "ontem"},
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
    await conn_ingest.commit()
    r = await cliente.get("/ata/siga_rj/S1")
    assert "javascript:" not in r.text


async def test_csv_neutraliza_formulas_e_baixa_como_anexo(cliente, conn_ingest):
    await conn_ingest.execute("UPDATE atas SET objeto = '=HYPERLINK(\"x\")' WHERE id_origem='A1'")
    await conn_ingest.commit()
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
