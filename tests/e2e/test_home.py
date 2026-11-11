"""Home (ADR 0039): a busca em destaque, sem lista, e o caminho para todas as atas."""

from __future__ import annotations

from comum import RESULTADOS, TODAS
from playwright.sync_api import Page, expect


def test_home_mostra_so_a_busca(page: Page, base_url):
    page.goto(base_url)
    expect(page.get_by_role("heading", level=1)).to_have_text("Atas de TI")
    expect(page.get_by_label("Buscar objeto ou item")).to_be_focused()
    expect(page.locator(RESULTADOS)).to_have_count(0)
    expect(page.locator(".lateral")).to_have_count(0)
    expect(page.locator(".home-rodape")).to_contain_text("Dados de")


def test_exemplo_de_busca_abre_os_resultados(page: Page, base_url):
    page.goto(base_url)
    page.locator(".exemplos").get_by_role("link", name="notebook").click()
    expect(page).to_have_url(f"{base_url}/?q=notebook")
    expect(page.locator(RESULTADOS)).to_have_text(["Aquisição de notebooks para a rede estadual"])


def test_ver_todas_as_atas_lista_sem_filtro(page: Page, base_url):
    page.goto(base_url)
    page.get_by_role("link", name="Ver todas as atas").click()
    expect(page).to_have_url(f"{base_url}{TODAS}")
    expect(page.locator(RESULTADOS).first).to_be_visible()
    expect(page.locator(".pilula")).to_have_count(0)


def test_marca_e_limpar_tudo_levam_de_volta_a_home(page: Page, base_url):
    page.goto(f"{base_url}/?q=notebook&uf=SP")
    page.get_by_role("link", name="Limpar tudo").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Atas de TI")
    page.goto(f"{base_url}/?q=notebook")
    page.locator(".marca").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Atas de TI")
