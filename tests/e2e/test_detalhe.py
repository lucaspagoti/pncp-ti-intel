"""Detalhe da ata: campos, itens, preço formatado, exportação e link de origem."""

from __future__ import annotations

from comum import RESULTADOS, TODAS
from playwright.sync_api import Page, expect


def test_detalhe_pela_busca(page: Page, base_url):
    page.goto(f"{base_url}/?q=impressao")
    page.get_by_role("link", name="Outsourcing de impressão departamental").click()
    expect(page).to_have_url(f"{base_url}/ata/compras_arp/A1")
    expect(page.get_by_role("heading", level=1)).to_have_text(
        "Outsourcing de impressão departamental"
    )
    expect(page.get_by_role("cell", name="Impressão A4 monocromática")).to_be_visible()
    expect(page.get_by_role("cell", name="R$ 0,12")).to_be_visible()
    expect(page.locator(".resumo-ata")).to_contain_text("MINISTERIO")
    origem = page.get_by_role("link", name="Conferir no portal")
    expect(origem).to_have_attribute("href", "https://pncp.gov.br/app/atas/1")
    expect(origem).to_have_attribute("rel", "noopener noreferrer")
    page.get_by_role("link", name="Voltar à busca").click()
    expect(page).to_have_url(f"{base_url}/?q=impressao")  # a busca como estava
    expect(page.locator(RESULTADOS)).to_have_text(["Outsourcing de impressão departamental"])


def test_voltar_depois_de_acesso_direto_a_outra_ata_leva_a_todas(page: Page, base_url):
    """QA-004 (W5): vir por um cartão não vale para outra ata aberta pela barra de endereço."""
    page.goto(f"{base_url}/?q=impressao")
    page.get_by_role("link", name="Outsourcing de impressão departamental").click()
    page.goto(f"{base_url}/ata/siga_rj/S1")
    page.get_by_role("link", name="Voltar à busca").click()
    expect(page).to_have_url(f"{base_url}{TODAS}")


def test_voltar_sem_historico_leva_a_todas_as_atas(page: Page, base_url):
    page.goto(f"{base_url}/ata/compras_arp/A1")
    page.get_by_role("link", name="Voltar à busca").click()
    expect(page).to_have_url(f"{base_url}{TODAS}")


def test_exportar_itens(page: Page, base_url):
    page.goto(f"{base_url}/ata/siga_rj/S1")
    with page.expect_download() as download:
        page.get_by_role("link", name="Exportar itens").click()
    assert download.value.suggested_filename == "itens_ata.csv"


def test_ata_sem_itens(page: Page, base_url):
    page.goto(f"{base_url}/ata/compras_arp/A2")
    expect(page.get_by_text("Esta fonte não traz itens para esta ata.")).to_be_visible()
    expect(page.get_by_role("link", name="Exportar itens")).to_have_count(0)
    expect(page.locator(".resumo-ata .prazo.crit")).to_have_text("vence em 5 dias")


def test_ata_inexistente_da_404(page: Page, base_url):
    resposta = page.goto(f"{base_url}/ata/compras_arp/NAO-EXISTE")
    assert resposta.status == 404
