"""Busca pela página inicial: resultado, estado vazio e paginação."""

from __future__ import annotations

from playwright.sync_api import Page, expect

RESULTADOS = "#resultados article.card h2 a"
# O botão não tem nome acessível hoje (label só com &nbsp;); a W2 corrige e o E2E
# passa a localizá-lo pelo papel.
BUSCAR = "form.busca button[type=submit]"


def test_busca_notebook_lista_a_ata(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Buscar objeto ou item").fill("notebook")
    page.locator(BUSCAR).click()
    expect(page.locator(RESULTADOS)).to_have_text(["Aquisição de notebooks para a rede estadual"])
    expect(page).to_have_url(
        f"{base_url}/?q=notebook&fonte=&esfera=&uf=&orgao=&vence_ate=&preco_min=&preco_max=&ordem=relevancia"
    )


def test_busca_sem_resultado_mostra_estado_vazio(page: Page, base_url):
    page.goto(f"{base_url}/?q=termoinexistentexyz")
    expect(page.get_by_text("Nenhuma ata encontrada para esses filtros.")).to_be_visible()
    expect(page.locator(".resumo")).to_contain_text("0 atas")


def test_paginacao(page: Page, base_url):
    page.goto(f"{base_url}/?q=cabo")
    expect(page.locator(".resumo")).to_contain_text("30 atas · página 1 de 2")
    expect(page.locator(RESULTADOS)).to_have_count(25)
    page.get_by_role("link", name="Próxima ›").click()
    expect(page.locator(".resumo")).to_contain_text("página 2 de 2")
    expect(page.locator(RESULTADOS)).to_have_count(5)
    expect(page.get_by_role("link", name="‹ Anterior")).to_be_visible()
