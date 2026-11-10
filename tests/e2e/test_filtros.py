"""Filtros pelo HTMX: trocam a casca (facetas, pílulas e resultados) e atualizam a URL."""

from __future__ import annotations

from datetime import timedelta

import web_dados
from comum import RESULTADOS, buscar
from playwright.sync_api import Page, expect

NOTEBOOK = "Aquisição de notebooks para a rede estadual"


def test_filtro_de_fonte_troca_resultados_sem_recarregar(page: Page, base_url):
    page.goto(base_url)
    page.evaluate("window.__sem_recarga = true")
    with page.expect_request(lambda r: r.headers.get("hx-request") == "true"):
        page.get_by_label("SIGA RJ").check()
    expect(page.locator(RESULTADOS)).to_have_text([NOTEBOOK])
    expect(page).to_have_url(
        f"{base_url}/?fonte=siga_rj&esfera=&uf=&orgao=&vigente_ate=&preco_min=&preco_max=&q=&ordem=relevancia"
    )
    expect(page.locator(".pilula")).to_contain_text(["Fonte: SIGA RJ"])
    assert page.evaluate("window.__sem_recarga") is True
    # A pílula remove o filtro, ainda pelo HTMX.
    page.get_by_label("Remover fonte").click()
    expect(page.locator(".pilula")).to_have_count(0)
    expect(page.get_by_label("Todas").first).to_be_checked()
    assert page.evaluate("window.__sem_recarga") is True


def test_voltar_do_navegador_restaura_a_busca(page: Page, base_url):
    page.goto(f"{base_url}/?q=impressao")
    page.get_by_label("Ordenar por").select_option("vencimento")
    expect(page).to_have_url(
        f"{base_url}/?fonte=&esfera=&uf=&orgao=&vigente_ate=&preco_min=&preco_max=&q=impressao&ordem=vencimento"
    )
    page.go_back()
    expect(page).to_have_url(f"{base_url}/?q=impressao")
    expect(page.locator(RESULTADOS)).to_have_text(["Outsourcing de impressão departamental"])
    expect(page.get_by_label("Ordenar por")).to_have_value("relevancia")


def test_vigente_ate_pelo_menos(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Vigente até pelo menos").fill(str(web_dados.HOJE + timedelta(days=100)))
    page.get_by_role("button", name="Aplicar filtros").click()
    expect(page.locator(RESULTADOS)).to_have_count(1)
    expect(page.locator(RESULTADOS)).to_contain_text(["toner"])


def test_faixa_de_preco(page: Page, base_url):
    page.goto(base_url)
    page.get_by_label("Preço unitário mínimo").fill("1000")
    page.get_by_label("Preço unitário máximo").fill("5000,00")
    buscar(page)
    expect(page.locator(RESULTADOS)).to_have_text([NOTEBOOK])
    expect(page.get_by_label("Preço unitário máximo")).to_have_value("5000,00")
    expect(page.locator(".pilula")).to_contain_text(
        ["Preço mín.: R$ 1000", "Preço máx.: R$ 5000,00"]
    )
