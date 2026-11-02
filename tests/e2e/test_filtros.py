"""Filtros pelo HTMX: troca só o bloco de resultados e atualiza a URL."""

from __future__ import annotations

from datetime import date, timedelta

from playwright.sync_api import Page, expect

RESULTADOS = "#resultados article.card h2 a"
# O botão não tem nome acessível hoje (label só com &nbsp;); a W2 corrige e o E2E
# passa a localizá-lo pelo papel.
BUSCAR = "form.busca button[type=submit]"


def test_filtro_de_fonte_troca_resultados_sem_recarregar(page: Page, base_url):
    page.goto(base_url)
    page.evaluate("window.__sem_recarga = true")
    with page.expect_request(lambda r: r.headers.get("hx-request") == "true"):
        page.get_by_label("Fonte").select_option("siga_rj")
    expect(page.locator(RESULTADOS)).to_have_text(["Aquisição de notebooks para a rede estadual"])
    expect(page).to_have_url(
        f"{base_url}/?q=&fonte=siga_rj&esfera=&uf=&orgao=&vigente_ate=&preco_min=&preco_max=&ordem=relevancia"
    )
    assert page.evaluate("window.__sem_recarga") is True


def test_vigente_ate_pelo_menos(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Vigente até pelo menos").fill(str(date.today() + timedelta(days=100)))
    page.locator(BUSCAR).click()
    expect(page.locator(RESULTADOS)).to_have_count(1)
    expect(page.locator(RESULTADOS)).to_contain_text(["toner"])


def test_faixa_de_preco(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Preço unitário mín. (R$)").fill("1000")
    page.get_by_label("Preço unitário máx. (R$)").fill("5000,00")
    page.locator(BUSCAR).click()
    expect(page.locator(RESULTADOS)).to_have_text(["Aquisição de notebooks para a rede estadual"])
    expect(page.get_by_label("Preço unitário máx. (R$)")).to_have_value("5000,00")
