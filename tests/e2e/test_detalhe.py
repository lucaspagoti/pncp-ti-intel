"""Detalhe da ata: itens, preço formatado, participantes e link de origem."""

from __future__ import annotations

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
    origem = page.get_by_role("link", name="Abrir no portal")
    expect(origem).to_have_attribute("href", "https://pncp.gov.br/app/atas/1")
    expect(origem).to_have_attribute("rel", "noopener noreferrer")


def test_detalhe_siga_mostra_participantes(page: Page, base_url):
    page.goto(f"{base_url}/ata/siga_rj/S1")
    expect(page.get_by_role("heading", name="Participantes: demandado × consumido")).to_be_visible()
    expect(page.get_by_role("cell", name="SEFAZ")).to_be_visible()


def test_ata_inexistente_da_404(page: Page, base_url):
    resposta = page.goto(f"{base_url}/ata/compras_arp/NAO-EXISTE")
    assert resposta.status == 404
