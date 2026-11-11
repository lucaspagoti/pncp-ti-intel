"""Cabeçalhos de segurança, autoescape e nenhuma violação de CSP no navegador."""

from __future__ import annotations

from comum import RESULTADOS
from playwright.sync_api import Page, expect

from pncp_ti.web.app import CABECALHOS_SEGURANCA


def test_cabecalhos_de_seguranca(page: Page, base_url):
    resposta = page.goto(base_url)
    cabecalhos = resposta.headers
    for nome, valor in CABECALHOS_SEGURANCA.items():
        assert cabecalhos[nome.lower()] == valor
    assert "unsafe-inline" not in cabecalhos["content-security-policy"]


def test_navegacao_sem_erros_de_console_nem_csp(page: Page, base_url, erros_console):
    page.goto(f"{base_url}/?q=microsoft")
    # O objeto traz <script>: aparece como texto, sem executar.
    expect(page.locator(RESULTADOS)).to_contain_text(["<script>alert(1)</script>"])
    page.get_by_label("Compras ARP").check()
    expect(page.locator(RESULTADOS)).to_have_count(1)
    page.goto(f"{base_url}/ata/siga_rj/S1")
    page.emulate_media(media="print")
    page.set_viewport_size({"width": 390, "height": 844})
    page.emulate_media(media="screen")
    page.goto(base_url)
    page.get_by_label("Buscar objeto ou item").fill("notebook")
    page.get_by_role("button", name="Buscar", exact=True).click()
    page.get_by_label("Fechar aviso").click()
    assert erros_console == []
