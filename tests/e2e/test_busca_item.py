"""W3 (ADR 0036): a linha do item que casou com a busca e o "você quis dizer"."""

from __future__ import annotations

from comum import RESULTADOS
from playwright.sync_api import Page, expect


def test_resultado_mostra_o_item_que_casou(page: Page, base_url):
    page.goto(f"{base_url}/?q=impressao")
    casado = page.locator(".resultados .ata-item").first
    expect(casado).to_contain_text("Impressão A4 monocromática")
    expect(casado.locator("mark")).to_have_text("Impressão")
    expect(casado).to_contain_text("1 de 1 item")
    expect(page.locator(".resultados .preco-nota").first).to_contain_text("do item buscado")


def test_voce_quis_dizer_leva_a_busca_corrigida(page: Page, base_url):
    page.goto(f"{base_url}/?q=impresao")
    expect(page.get_by_text("Você quis dizer")).to_be_visible()
    page.get_by_role("link", name="impressao").click()
    expect(page).to_have_url(f"{base_url}/?q=impressao")
    expect(page.locator(RESULTADOS).first).to_be_visible()
