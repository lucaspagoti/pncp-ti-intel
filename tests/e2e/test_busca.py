"""Busca pela home e pela barra da lista: resultado, estado vazio e paginação."""

from __future__ import annotations

from comum import RESULTADOS, buscar
from playwright.sync_api import Page, expect


def test_busca_notebook_lista_a_ata(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Buscar objeto ou item").fill("notebook")
    buscar(page)
    expect(page.locator(RESULTADOS)).to_have_text(["Aquisição de notebooks para a rede estadual"])
    expect(page).to_have_url(f"{base_url}/?q=notebook")
    expect(page.get_by_role("heading", level=1)).to_have_text("1 ata vigente")


def test_enter_no_campo_busca(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Buscar objeto ou item").fill("impressao")
    page.get_by_label("Buscar objeto ou item").press("Enter")
    expect(page.locator(RESULTADOS)).to_have_text(["Outsourcing de impressão departamental"])


def test_busca_pela_barra_da_lista_troca_sem_recarregar(page: Page, base_url):
    page.goto(f"{base_url}/?q=notebook")
    page.evaluate("window.__sem_recarga = true")
    page.get_by_label("Buscar objeto ou item").fill("impressao")
    buscar(page)
    expect(page.locator(RESULTADOS)).to_have_text(["Outsourcing de impressão departamental"])
    assert page.evaluate("window.__sem_recarga") is True


def test_busca_sem_resultado_mostra_estado_vazio(page: Page, base_url):
    page.goto(f"{base_url}/?q=termoinexistentexyz")
    expect(page.get_by_text("Nenhuma ata encontrada para esses filtros.")).to_be_visible()
    expect(page.get_by_role("heading", level=1)).to_have_text("0 atas vigentes")


def test_paginacao(page: Page, base_url):
    page.goto(f"{base_url}/?q=cabo")
    expect(page.get_by_role("heading", level=1)).to_have_text("30 atas vigentes")
    expect(page.locator(RESULTADOS)).to_have_count(20)
    expect(page.locator(".pag [aria-current=page]")).to_have_text("1")
    page.get_by_role("link", name="Próxima").click()
    expect(page.locator(".pag")).to_have_attribute("aria-label", "Paginação, página 2 de 2")
    expect(page.locator(".pag [aria-current=page]")).to_have_text("2")
    expect(page.locator(RESULTADOS)).to_have_count(10)
    expect(page).to_have_url(f"{base_url}/?q=cabo&pagina=2")
    page.get_by_role("link", name="Página 1").click()
    expect(page.locator(RESULTADOS)).to_have_count(20)
