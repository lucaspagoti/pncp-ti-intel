"""Home (ADR 0039): a busca em destaque, sem lista, e o caminho para todas as atas."""

from __future__ import annotations

import pytest
from comum import RESULTADOS, TODAS
from conftest import CELULAR, DESKTOP
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


def _centro(page: Page, seletor: str) -> float:
    return page.evaluate(
        "(s) => { const r = document.querySelector(s).getBoundingClientRect();"
        " return r.left + r.width / 2; }",
        seletor,
    )


@pytest.mark.parametrize("tela", [DESKTOP, CELULAR], ids=["desktop", "celular"])
def test_campo_de_busca_fica_no_eixo_do_titulo(page: Page, base_url, tela):
    """ADR 0040: o botão mora dentro do campo, e o campo não sai do centro da home."""
    page.set_viewport_size(tela)
    page.goto(base_url)
    titulo = _centro(page, ".home h1")
    for seletor in (".campo-busca", ".exemplos", ".home-rodape"):
        assert abs(_centro(page, seletor) - titulo) <= 1, seletor


def test_home_sem_rotulo_experimente_e_com_rodape_legivel(page: Page, base_url):
    page.goto(base_url)
    expect(page.get_by_text("Experimente")).to_have_count(0)
    rodape = page.locator(".home-rodape").inner_text()
    assert "20" in rodape and "ões" not in rodape
    assert ".SIGA" not in rodape and ". SIGA" in rodape  # a quebra escondida não cola as frases


def test_botao_de_busca_apagado_com_o_campo_vazio(page: Page, base_url):
    page.goto(base_url)
    botao = page.get_by_role("button", name="Buscar", exact=True)
    expect(botao).to_have_css("background-color", "rgba(29, 29, 31, 0.06)")  # apagado
    page.get_by_label("Buscar objeto ou item").fill("notebook")
    expect(botao).to_have_css("background-color", "rgb(29, 29, 31)")  # grafite, sem o azul de antes


def test_inter_carrega_da_propria_web_sem_violar_a_csp(page: Page, base_url, erros_console):
    page.goto(base_url)
    page.evaluate("document.fonts.ready")
    carregada = page.evaluate(
        "[...document.fonts].some((f) => f.family.includes('Inter') && f.status === 'loaded')"
    )
    assert carregada
    familia = page.evaluate("getComputedStyle(document.body).fontFamily")
    assert familia.startswith("Inter")
    assert erros_console == []
