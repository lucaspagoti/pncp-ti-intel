"""W2: desktop 1366 e celular 390, impressão, contraste e captura de referência visual."""

from __future__ import annotations

from pathlib import Path

import pytest
from comum import CONTRASTE_JS, RESULTADOS
from conftest import CELULAR, DESKTOP
from playwright.sync_api import Page, expect

TELAS = {"busca": "/?q=impressao", "busca-vazia": "/", "detalhe": "/ata/siga_rj/S1"}


def _sem_rolagem_horizontal(page: Page) -> None:
    largura = page.evaluate("document.documentElement.scrollWidth")
    assert largura <= page.viewport_size["width"], largura


@pytest.mark.parametrize("tela", [DESKTOP, CELULAR], ids=["desktop", "celular"])
def test_capturas_de_referencia_sem_rolagem_horizontal(page: Page, base_url, pytestconfig, tela):
    saida = Path(pytestconfig.getoption("output")) / "referencia"
    saida.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size(tela)
    for nome, url in TELAS.items():
        page.goto(base_url + url)
        _sem_rolagem_horizontal(page)
        page.screenshot(path=saida / f"{nome}-{tela['width']}.png", full_page=True)


def test_desktop_mostra_lateral_com_filtros(page: Page, base_url):
    page.goto(base_url)
    expect(page.locator(".lateral")).to_be_visible()
    expect(page.get_by_label("UF")).to_be_visible()
    expect(page.locator(".rodape-lateral")).to_contain_text("Dados de")


def test_celular_recolhe_filtros_e_mantem_aberto_apos_filtrar(page: Page, base_url):
    page.set_viewport_size(CELULAR)
    page.goto(base_url)
    expect(page.get_by_label("UF")).to_be_hidden()
    page.locator(".titulo-filtros").click()
    expect(page.get_by_label("UF")).to_be_visible()
    page.get_by_label("SIGA RJ").check()
    expect(page.locator(RESULTADOS)).to_have_count(1)
    expect(page.get_by_label("UF")).to_be_visible()  # hx-preserve no alternador
    # Abaixo de 600px a tabela empilha e o preço unitário continua visível.
    expect(page.locator(".resultados td.preco").first).to_be_visible()


def test_impressao_esconde_lateral_busca_e_paginacao(page: Page, base_url):
    page.goto(f"{base_url}/?q=impressao")
    page.emulate_media(media="print")
    for seletor in (".lateral", ".busca", ".pag"):
        expect(page.locator(seletor)).to_be_hidden()
    expect(page.locator(RESULTADOS)).to_be_visible()
    page.goto(f"{base_url}/ata/siga_rj/S1")
    expect(page.locator(".acoes-registro")).to_be_hidden()
    expect(page.locator(".campos")).to_be_visible()


@pytest.mark.parametrize(
    ("url", "seletor"),
    [
        ("/?q=microsoft", ".resultados td.objeto > a"),
        ("/?q=microsoft", ".resultados .sub"),
        ("/?q=microsoft", ".chip.crit"),
        ("/?q=notebook", ".chip.warn"),
        ("/?q=notebook", ".resultados th"),
        ("/?q=notebook", ".opcao .qtd"),
        ("/?q=notebook", ".rodape-lateral"),
        ("/?q=notebook", ".botao"),
        ("/?q=notebook", ".pilula"),
        ("/?q=notebook", ".nota"),
        ("/ata/siga_rj/S1", ".campos dt"),
        ("/ata/siga_rj/S1", ".ident"),
        ("/ata/siga_rj/S1", ".chip"),
    ],
)
def test_contraste_minimo_de_texto(page: Page, base_url, url, seletor):
    page.goto(base_url + url)
    razao = page.evaluate(CONTRASTE_JS, seletor)
    assert razao is not None, seletor
    assert razao >= 4.5, f"{seletor}: {razao:.2f}"


@pytest.mark.parametrize("tela", [DESKTOP, CELULAR], ids=["desktop", "celular"])
def test_texto_longo_sem_espaco_nao_alarga_a_pagina(page: Page, base_url, tela):
    """QA-001: termo, órgão e objeto sem espaço quebram em vez de criar rolagem horizontal."""
    page.set_viewport_size(tela)
    for url in (
        f"/?q={'x' * 200}",
        f"/?orgao={'x' * 200}",
        "/?q=zzzlongo",
        "/ata/compras_arp/LONGO",
    ):
        page.goto(base_url + url)
        _sem_rolagem_horizontal(page)
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    page.goto(f"{base_url}/?q={'x' * 200}")
    expect(page.get_by_label("Remover termo")).to_be_visible()
