"""Busca pela página inicial: resultado, estado vazio e paginação."""

from __future__ import annotations

from comum import RESULTADOS, buscar
from playwright.sync_api import Page, expect


def test_busca_notebook_lista_a_ata(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Buscar objeto ou item").fill("notebook")
    buscar(page)
    expect(page.locator(RESULTADOS)).to_have_text(["Aquisição de notebooks para a rede estadual"])
    expect(page).to_have_url(
        f"{base_url}/?fonte=&esfera=&uf=&orgao=&vigente_ate=&preco_min=&preco_max=&q=notebook&ordem=relevancia"
    )
    expect(page.locator(".contador").first).to_have_text("1")


def test_enter_no_campo_busca(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Buscar objeto ou item").fill("impressao")
    page.get_by_label("Buscar objeto ou item").press("Enter")
    expect(page.locator(RESULTADOS)).to_have_text(["Outsourcing de impressão departamental"])


def test_busca_sem_resultado_mostra_estado_vazio(page: Page, base_url):
    page.goto(f"{base_url}/?q=termoinexistentexyz")
    expect(page.get_by_text("Nenhuma ata encontrada para esses filtros.")).to_be_visible()
    expect(page.locator(".contador").first).to_have_text("0")


def test_paginacao(page: Page, base_url):
    page.goto(f"{base_url}/?q=cabo")
    expect(page.locator(".barra")).to_contain_text("Mostrando 1 a 20 de 30 atas vigentes")
    expect(page.locator(RESULTADOS)).to_have_count(20)
    page.get_by_role("link", name="Próxima").click()
    expect(page.locator(".barra")).to_contain_text("Mostrando 21 a 30 de 30")
    expect(page.locator(".pag")).to_contain_text("Página 2 de 2")
    expect(page.locator(RESULTADOS)).to_have_count(10)
    expect(page).to_have_url(f"{base_url}/?q=cabo&pagina=2")
    expect(page.get_by_role("link", name="Anterior")).to_be_visible()
