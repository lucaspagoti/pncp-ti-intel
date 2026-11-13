"""W2 e W5: desktop 1366 e celular 390, impressão, contraste e captura de referência visual."""

from __future__ import annotations

from pathlib import Path

import pytest
from comum import CONTRASTE_JS, RESULTADOS, TODAS
from conftest import CELULAR, DESKTOP
from playwright.sync_api import Page, expect

TELAS = {
    "home": "/",
    "busca": "/?q=impressao",
    "todas": TODAS,
    "detalhe": "/ata/siga_rj/S1",
}


def _sem_rolagem_horizontal(page: Page) -> None:
    largura = page.evaluate("document.documentElement.scrollWidth")
    assert largura <= page.viewport_size["width"], largura


@pytest.mark.parametrize("tela", [DESKTOP, CELULAR], ids=["desktop", "celular"])
def test_capturas_de_referencia_sem_rolagem_horizontal(page: Page, base_url, pytestconfig, tela):
    saida = Path(pytestconfig.getoption("output")) / "referencia"
    saida.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size(tela)
    for nome, url in TELAS.items():
        page.goto(base_url + url)
        _sem_rolagem_horizontal(page)
        page.screenshot(path=saida / f"{nome}-{tela['width']}.png", full_page=True)


def test_desktop_mostra_lateral_com_filtros(page: Page, base_url):
    page.goto(base_url + TODAS)
    expect(page.locator(".lateral")).to_be_visible()
    expect(page.get_by_label("UF")).to_be_visible()
    expect(page.locator(".rodape-lateral")).to_contain_text("Dados de")


def test_tela_larga_centraliza_lateral_e_lista_juntas(page: Page, base_url):
    """W12: em monitor largo, lateral e lista ficam juntas no meio; a lista mantém 1000 px."""
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(base_url + TODAS)
    casca = page.locator(".casca").bounding_box()
    largura = page.evaluate("document.documentElement.clientWidth")
    esquerda, direita = casca["x"], largura - casca["x"] - casca["width"]
    assert esquerda > 200 and abs(esquerda - direita) <= 1, (esquerda, direita)
    lateral = page.locator(".lateral").bounding_box()
    lista = page.locator(".lista-atas").bounding_box()
    assert lista["width"] == 1000 and lista["x"] - (lateral["x"] + lateral["width"]) <= 16
    _sem_rolagem_horizontal(page)


def test_tela_de_ate_1296_continua_sem_margem_externa(page: Page, base_url):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + TODAS)
    assert page.locator(".casca").bounding_box()["x"] == 0


def test_celular_recolhe_filtros_e_mantem_aberto_apos_filtrar(page: Page, base_url):
    page.set_viewport_size(CELULAR)
    page.goto(base_url + TODAS)
    expect(page.get_by_label("UF")).to_be_hidden()
    page.locator(".botao-filtros").click()
    expect(page.get_by_label("UF")).to_be_visible()
    page.get_by_label("SIGA RJ").check()
    expect(page.locator(RESULTADOS)).to_have_count(1)
    expect(page.get_by_label("UF")).to_be_visible()  # hx-preserve no alternador
    # No celular o cartão empilha e o preço continua visível.
    expect(page.locator(".resultados .preco").first).to_be_visible()


def test_impressao_esconde_lateral_busca_e_paginacao(page: Page, base_url):
    page.goto(f"{base_url}/?q=cabo")
    page.emulate_media(media="print")
    for seletor in (".lateral", ".busca", ".pag", ".aviso"):
        expect(page.locator(seletor)).to_be_hidden()
    expect(page.locator(RESULTADOS).first).to_be_visible()
    page.goto(f"{base_url}/ata/siga_rj/S1")
    page.emulate_media(media="print")
    expect(page.locator(".acoes")).to_be_hidden()
    expect(page.locator(".resumo-ata")).to_be_visible()


@pytest.mark.parametrize(
    ("url", "seletor"),
    [
        ("/", ".home-lede"),
        ("/?q=notebook", ".marca"),
        ("/", ".categoria-qtd"),
        ("/", ".recortes .qtd.warn"),
        ("/", ".recortes .qtd:not(.warn)"),
        ("/", ".home-rodape"),
        ("/?q=microsoft", ".ata-objeto > a"),
        ("/?q=microsoft", ".ata-meta"),
        ("/?q=microsoft", ".prazo.crit"),
        ("/?q=notebook", ".prazo.warn"),
        ("/?q=notebook", ".preco-nota"),
        ("/?q=notebook", ".opcao .qtd"),  # a opção marcada: branco sobre o azul
        ("/?q=notebook", ".opcao:not(:has(input:checked)) .qtd"),
        ("/?q=notebook", ".rodape-lateral"),
        ("/?q=notebook", ".busca-botao"),
        ("/?q=notebook", ".pilula"),
        ("/?q=notebook", ".aviso p"),
        ("/?q=impressao", ".resultados .ata-item mark"),
        ("/?q=impressao", ".resultados .rotulo-item"),
        ("/ata/siga_rj/S1", ".resumo-ata dt"),
        ("/ata/siga_rj/S1", ".sobretitulo"),
        ("/ata/siga_rj/S1", ".sobre dt"),
        ("/ata/siga_rj/S1", ".sobre .legal"),
        ("/ata/siga_rj/S1", ".contagem"),
        ("/ata/compras_arp/A2", ".resumo-ata .prazo.crit"),
    ],
)
def test_contraste_minimo_de_texto(page: Page, base_url, url, seletor):
    page.goto(base_url + url)
    razao = page.evaluate(CONTRASTE_JS, seletor)
    assert razao is not None, seletor
    assert razao >= 4.5, f"{seletor}: {razao:.2f}"


@pytest.mark.parametrize("tela", [DESKTOP, CELULAR], ids=["desktop", "celular"])
def test_texto_longo_sem_espaco_nao_alarga_a_pagina(page: Page, base_url, tela):
    """QA-001: termo, órgão e objeto sem espaço quebram em vez de criar rolagem horizontal."""
    page.set_viewport_size(tela)
    for url in (
        f"/?q={'x' * 200}",
        f"/?orgao={'x' * 200}",
        "/?q=zzzlongo",
        "/ata/compras_arp/LONGO",
    ):
        page.goto(base_url + url)
        _sem_rolagem_horizontal(page)
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    page.goto(f"{base_url}/?q={'x' * 200}")
    expect(page.get_by_label("Remover termo")).to_be_visible()


def test_item_casado_e_sugestao_sem_espaco_nao_alargam_o_celular(page: Page, base_url):
    """QA-002 (W5): texto de terceiros sem espaço na linha do item e na sugestão do estado vazio."""
    page.set_viewport_size(CELULAR)
    page.goto(f"{base_url}/?q={'k' * 100}")
    expect(page.locator(".ata-item").first).to_be_visible()
    _sem_rolagem_horizontal(page)
    page.goto(f"{base_url}/?q={'y' * 100}")  # sem resultado: sugere a palavra de 250 letras
    expect(page.get_by_text("Você quis dizer")).to_be_visible()
    _sem_rolagem_horizontal(page)


def test_numero_do_item_fica_numa_linha(page: Page, base_url):
    """No ARP real o item é `00001`; a quebra de texto da tabela não pode partir o número."""
    page.goto(f"{base_url}/ata/compras_arp/LONGO")
    linhas = page.evaluate(
        """() => [...document.querySelectorAll('td.num-item')].map((td) => {
             const r = document.createRange(); r.selectNodeContents(td);
             return r.getClientRects().length; })"""
    )
    assert linhas == [1, 1, 1], linhas


def test_impressao_com_descricao_sem_espaco_cabe_na_folha(page: Page, base_url):
    """R2-001: na área útil do A4 com margem (~718 px), a tabela cabe e o preço fica na folha."""
    page.set_viewport_size({"width": 718, "height": 1123})
    page.goto(f"{base_url}/ata/compras_arp/LONGO")
    page.emulate_media(media="print")
    largura = page.evaluate("document.querySelector('.itens table').scrollWidth")
    assert largura <= 718, largura
    expect(page.get_by_role("cell", name="R$ 9,99")).to_be_visible()
    linhas = page.evaluate(
        """() => [...document.querySelectorAll('td.num-item')].map((td) => {
             const r = document.createRange(); r.selectNodeContents(td);
             return r.getClientRects().length; })"""
    )
    assert linhas == [1, 1, 1], linhas


def test_celular_alvos_de_toque_de_44px(page: Page, base_url):
    page.set_viewport_size(CELULAR)
    page.goto(f"{base_url}/?q=cabo")
    alvos = [
        page.get_by_label("Remover termo"),
        page.get_by_role("link", name="Próxima"),
        page.get_by_role("link", name="Página 2"),
        page.locator(".botao-filtros"),
        page.locator(".fechar"),
        page.get_by_role("button", name="Buscar", exact=True),
    ]
    for alvo in alvos:
        caixa = alvo.bounding_box()
        assert caixa and caixa["height"] >= 44 and caixa["width"] >= 44, caixa


def _alvos_de_44px(alvos) -> None:
    assert alvos
    for alvo in alvos:
        caixa = alvo.bounding_box()
        assert caixa and caixa["height"] >= 44, (alvo.inner_text(), caixa)


def test_celular_opcoes_links_categorias_e_recortes_com_alvo_de_44px(page: Page, base_url):
    """QA-003 (W5): as opções de filtro e os links soltos também têm 44 px de toque."""
    page.set_viewport_size(CELULAR)
    page.goto(base_url)
    _alvos_de_44px(page.locator(".categoria").all())
    _alvos_de_44px(page.locator(".recortes a").all())
    page.goto(base_url + TODAS)
    page.locator(".botao-filtros").click()
    _alvos_de_44px(page.locator(".opcao").all())
    _alvos_de_44px([page.get_by_role("link", name="Limpar", exact=True), page.locator(".marca")])
    page.goto(f"{base_url}/?q=notebook&uf=SP")
    _alvos_de_44px([page.get_by_role("link", name="Limpar tudo")])
    page.goto(f"{base_url}/ata/compras_arp/LONGO")
    _alvos_de_44px([page.get_by_role("link", name="Voltar à busca")])


def test_estado_vazio_orienta_o_proximo_passo(page: Page, base_url):
    page.goto(f"{base_url}/?q=termoinexistentexyz")
    expect(page.get_by_text("Tire um filtro acima")).to_be_visible()
    page.get_by_role("link", name="comece uma busca nova").click()
    expect(page).to_have_url(f"{base_url}/")
    expect(page.get_by_role("heading", level=1)).to_have_text("Portal de Atas de TI")


def test_casca_fica_ocupada_durante_a_busca(page: Page, base_url):
    page.goto(base_url + TODAS)
    page.route("**/?*", lambda rota: (page.wait_for_timeout(600), rota.continue_()))
    page.get_by_label("SIGA RJ").check()
    expect(page.locator("#casca")).to_have_attribute("aria-busy", "true")
    # A barra de progresso corre enquanto a resposta não chega.
    expect(page.locator("html")).to_have_attribute("data-ocupado", "")
    expect(page.locator("#casca")).not_to_have_attribute("aria-busy", "true")
    expect(page.locator("html")).not_to_have_attribute("data-ocupado", "")


def test_especificacao_longa_abre_no_detalhe_e_sai_inteira_na_impressao(page: Page, base_url):
    page.goto(f"{base_url}/ata/compras_arp/LONGO")
    espec = page.locator("details.espec").first
    expect(espec.locator("p")).to_be_hidden()
    espec.locator("summary").click()
    expect(espec.locator("p")).to_be_visible()
    page.emulate_media(media="print")
    expect(page.locator(".itens .impressao").first).to_be_visible()
    expect(espec).to_be_hidden()


def test_aviso_fechado_nao_volta(page: Page, base_url):
    page.goto(base_url + TODAS)
    aviso = page.locator("[data-dispensar]")
    expect(aviso).to_be_visible()
    page.get_by_label("Fechar aviso").click()
    expect(aviso).to_be_hidden()
    page.reload()
    expect(page.locator(RESULTADOS).first).to_be_visible()
    expect(aviso).to_be_hidden()
    page.get_by_label("SIGA RJ").check()  # e a troca do HTMX também o mantém fechado
    expect(page.locator(RESULTADOS)).to_have_count(1)
    expect(aviso).to_be_hidden()


def test_movimento_reduzido_desliga_as_transicoes(page: Page, base_url):
    page.emulate_media(reduced_motion="reduce")
    page.goto(base_url + TODAS)
    duracao = page.evaluate(
        "getComputedStyle(document.querySelector('.busca-botao')).transitionDuration"
    )
    assert duracao.split(",")[0].strip() in ("0.001s", "0s"), duracao


def test_barra_de_progresso_aparece_quando_a_casca_esta_ocupada(page: Page, base_url):
    page.goto(base_url + TODAS)
    expect(page.locator(".progresso")).to_have_css("opacity", "0")
    page.evaluate("document.documentElement.setAttribute('data-ocupado', '')")
    expect(page.locator(".progresso")).to_have_css("opacity", "1")
