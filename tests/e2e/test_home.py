"""Home (ADR 0039): a busca em destaque, sem lista, e o caminho para todas as atas."""

from __future__ import annotations

import re

import pytest
from comum import RESULTADOS, TODAS
from conftest import CELULAR, DESKTOP
from playwright.sync_api import Page, expect


def test_home_mostra_so_a_busca(page: Page, base_url):
    page.goto(base_url)
    expect(page.get_by_role("heading", level=1)).to_have_text("Portal de Atas de TI")
    expect(page.get_by_label("Buscar objeto ou item")).to_be_focused()
    expect(page.locator(RESULTADOS)).to_have_count(0)
    expect(page.locator(".lateral")).to_have_count(0)
    expect(page.locator(".home-rodape")).to_contain_text("Dados de")


def test_categoria_abre_a_lista_filtrada(page: Page, base_url):
    page.goto(base_url)
    page.locator(".categorias").get_by_role("link", name="Computadores").click()
    expect(page).to_have_url(f"{base_url}/?categoria=computadores")
    expect(page.locator(RESULTADOS).filter(has_text="notebooks")).to_have_count(1)
    expect(page.locator(".pilula")).to_have_text(re.compile(r"Categoria\s+Computadores"))
    # Tirar a pílula (último filtro) mantém a lista de todas as atas, não volta para a home.
    page.get_by_label("Remover categoria").click()
    expect(page.locator(".pilula")).to_have_count(0)
    expect(page.locator(RESULTADOS).first).to_be_visible()


def test_categoria_mantida_ao_mudar_outro_filtro(page: Page, base_url):
    page.goto(f"{base_url}/?categoria=computadores")
    page.get_by_label("Ordenar por").select_option("vencimento")
    expect(page).to_have_url(re.compile(r"categoria=computadores"))
    expect(page.locator(".pilula")).to_have_text(re.compile(r"Categoria\s+Computadores"))


def test_recortes_levam_a_listas_prontas(page: Page, base_url):
    page.goto(base_url)
    page.locator(".recortes").get_by_role("link", name="Vencem em 30 dias").click()
    expect(page).to_have_url(re.compile(r"vence_ate=\d{4}-\d{2}-\d{2}&ordem=vencimento"))
    expect(page.locator(".pilula")).to_have_text(re.compile(r"Vence até"))
    page.goto(base_url)
    page.locator(".recortes").get_by_role("link", name="Rio de Janeiro").click()
    expect(page).to_have_url(f"{base_url}/?uf=RJ")


@pytest.mark.parametrize(
    ("tela", "colunas"), [(DESKTOP, 4), (CELULAR, 2)], ids=["desktop", "celular"]
)
def test_grade_de_categorias_tem_4_colunas_e_2_no_celular(page: Page, base_url, tela, colunas):
    page.set_viewport_size(tela)
    page.goto(base_url)
    expect(page.locator(".categoria")).to_have_count(8)
    usadas = page.evaluate(
        "() => new Set([...document.querySelectorAll('.categoria')]"
        ".map(e => Math.round(e.getBoundingClientRect().left))).size"
    )
    assert usadas == colunas
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_ver_todas_as_atas_lista_sem_filtro(page: Page, base_url):
    page.goto(base_url)
    page.locator(".recortes").get_by_role("link", name="Todas as atas").click()
    expect(page).to_have_url(f"{base_url}{TODAS}")
    expect(page.locator(RESULTADOS).first).to_be_visible()
    expect(page.locator(".pilula")).to_have_count(0)


def test_marca_e_limpar_tudo_levam_de_volta_a_home(page: Page, base_url):
    page.goto(f"{base_url}/?q=notebook&uf=SP")
    page.get_by_role("link", name="Limpar tudo").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Portal de Atas de TI")
    page.goto(f"{base_url}/?q=notebook")
    page.locator(".marca").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Portal de Atas de TI")


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
    for seletor in (".campo-busca", ".categorias", ".recortes", ".home-rodape"):
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


def test_marca_com_o_nome_e_o_icone_do_portal(page: Page, base_url):
    page.goto(base_url)
    expect(page).to_have_title("Portal de Atas de TI")
    expect(page.locator(".home .selo-grande")).to_be_visible()
    page.goto(f"{base_url}/?q=notebook")
    expect(page).to_have_title("notebook · Portal de Atas de TI")
    marca = page.locator(".marca")
    expect(marca).to_have_text("Portal de Atas de TI")
    assert marca.locator(".selo svg").count() == 1
    # O selo é do grafite do produto, sem o azul.
    expect(marca.locator(".selo")).to_have_css("background-color", "rgb(29, 29, 31)")


def test_marca_cabe_na_lateral_sem_quebrar_linha(page: Page, base_url):
    page.goto(f"{base_url}/?explorar=1")
    caixa = page.locator(".marca").bounding_box()
    assert caixa["height"] < 40, caixa  # uma linha só ("Portal de Atas de TI" ao lado do ícone)


def test_icone_da_aba_carrega(page: Page, base_url):
    for caminho, tipo in (("icone.svg", "image/svg+xml"), ("icone-32.png", "image/png")):
        resposta = page.request.get(f"{base_url}/static/{caminho}")
        assert resposta.ok and resposta.headers["content-type"].startswith(tipo)
    page.goto(base_url)
    ligacoes = page.evaluate(
        "[...document.querySelectorAll('link[rel~=icon], link[rel=apple-touch-icon]')]"
        ".map((l) => l.getAttribute('href'))"
    )
    assert "/static/icone.svg" in ligacoes and "/static/icone-apple-180.png" in ligacoes


def test_titulo_da_aba_acompanha_a_busca_e_a_remocao_do_termo(page: Page, base_url):
    """QA-W8-001: a troca pelo HTMX também muda o título da aba."""
    page.goto(f"{base_url}/?q=notebook")
    page.evaluate("window.__sem_recarga = true")
    page.get_by_label("Buscar objeto ou item").fill("impressao")
    page.get_by_role("button", name="Buscar", exact=True).click()
    expect(page).to_have_title("impressao · Portal de Atas de TI")
    page.get_by_label("Remover termo").click()
    expect(page).to_have_title("Portal de Atas de TI")
    assert page.evaluate("window.__sem_recarga") is True


@pytest.mark.parametrize("tela", [DESKTOP, CELULAR], ids=["desktop", "celular"])
def test_detalhe_tem_a_marca_em_uma_linha_e_leva_a_home(page: Page, base_url, tela):
    """QA-W8-002."""
    page.set_viewport_size(tela)
    page.goto(f"{base_url}/ata/siga_rj/S1")
    marca = page.locator(".detalhe-marca .marca")
    expect(marca).to_have_text("Portal de Atas de TI")
    caixa = marca.bounding_box()
    assert caixa["height"] < 50, caixa
    if tela is CELULAR:
        assert caixa["height"] >= 44, caixa
    marca.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", level=1)).to_have_text("Portal de Atas de TI")
    expect(page).to_have_url(f"{base_url}/")
