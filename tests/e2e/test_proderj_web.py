"""PRODERJ (ADR 0042): abas "Todas | PRODERJ" sobre a lista e botão da contratação no detalhe."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
import web_dados
from comum import CONTRASTE_JS, RESULTADOS, TODAS
from conftest import CELULAR
from playwright.sync_api import Page, expect

from pncp_ti.config import get_settings, ingest_dsn
from pncp_ti.fontes import proderj

PAGINA = "https://www.rj.gov.br/proderj/node/1779"
MICROSOFT = "SEI-430002/000030/2024"


@pytest.fixture(scope="module", autouse=True)
def atas_do_proderj(base_url, nome_banco_teste):
    """Duas atas do PRODERJ no SIGA só para este módulo; saem ao fim para não mexer nos outros."""
    dsn = ingest_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    with psycopg.connect(dsn) as conn:
        siga = conn.execute("SELECT id FROM cargas WHERE fonte = 'siga_rj' AND ativa").fetchone()[0]
        for comando, parametros in (
            web_dados.ata_proderj(siga, "P1", "MICROSOFT", MICROSOFT),
            web_dados.ata_proderj(siga, "P2", "OUTSOURCING DE IMPRESSÃO", "SEI-430002/009999/2025"),
        ):
            conn.execute(comando, parametros)
        carga = uuid4()
        conn.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa, concluido_em) "
            "VALUES (%s, 'proderj', current_date, 'concluida', true, now())",
            (carga,),
        )
        conn.execute(
            "INSERT INTO proderj_links VALUES (%s, %s, 1779, %s, 'PE-RP 012/2025', 'homologadas')",
            (carga, proderj.normalizar_processo(MICROSOFT), PAGINA),
        )
        conn.execute("SELECT atualizar_busca()")
    yield
    with psycopg.connect(dsn) as conn:
        conn.execute("DELETE FROM cargas WHERE fonte = 'proderj'")
        conn.execute("DELETE FROM atas WHERE id_origem IN ('P1', 'P2')")
        conn.execute("SELECT atualizar_busca()")


def test_aba_proderj_troca_a_lista_sem_recarregar(page: Page, base_url):
    page.goto(base_url + TODAS)
    page.evaluate("window.__sem_recarga = true")
    expect(page.get_by_role("radio", name="Todas as atas")).to_be_checked()
    with page.expect_request(lambda r: r.headers.get("hx-request") == "true"):
        page.get_by_label("PRODERJ").check()
    expect(page.locator(RESULTADOS)).to_have_text(["MICROSOFT", "OUTSOURCING DE IMPRESSÃO"])
    expect(page.get_by_role("heading", level=1)).to_have_text("2 atas vigentes")
    expect(page).to_have_url(
        f"{base_url}/?fonte=&esfera=&uf=&orgao=&vigente_ate=&preco_min=&preco_max=&q=&escopo=proderj&ordem=relevancia"
    )
    expect(page.locator(".pilula")).to_have_count(0)
    assert page.evaluate("window.__sem_recarga") is True
    page.get_by_label("Todas as atas").check()
    expect(page.get_by_role("heading", level=1)).not_to_have_text("2 atas vigentes")


def test_aba_proderj_funciona_pelo_teclado(page: Page, base_url):
    page.goto(base_url + TODAS)
    page.get_by_label("Todas as atas").focus()
    page.keyboard.press("ArrowRight")
    expect(page.get_by_label("PRODERJ")).to_be_checked()
    expect(page.locator(RESULTADOS)).to_have_count(2)


def test_aba_no_celular_cabe_e_tem_alvo_de_toque(page: Page, base_url):
    page.set_viewport_size(CELULAR)
    page.goto(f"{base_url}/?escopo=proderj")
    assert page.evaluate("document.documentElement.scrollWidth") <= CELULAR["width"]
    for aba in page.locator(".aba").all():
        assert aba.bounding_box()["height"] >= 44


def test_detalhe_leva_ao_site_do_proderj(page: Page, base_url):
    page.goto(f"{base_url}/ata/siga_rj/P1")
    botao = page.get_by_role("link", name="Ver no site do PRODERJ")
    expect(botao).to_have_attribute("href", PAGINA)
    expect(botao).to_have_attribute("target", "_blank")
    expect(botao).to_have_attribute("rel", "noopener noreferrer")


def test_detalhe_sem_pagina_mostra_botao_desativado_e_a_nota(page: Page, base_url):
    page.goto(f"{base_url}/ata/siga_rj/P2")
    botao = page.locator(".botao[aria-disabled='true']")
    expect(botao).to_have_text("Não consta no site do PRODERJ")
    expect(botao).not_to_have_attribute("href", "")
    assert botao.get_attribute("href") is None and botao.get_attribute("tabindex") is None
    expect(page.locator(".nota-acao")).to_contain_text("Confira no SIGA")
    page.keyboard.press("Tab")  # o botão desativado não entra na ordem de foco
    foco = [page.evaluate("document.activeElement.textContent") for _ in range(3)]
    assert not any("Não consta" in (t or "") for t in foco)
    assert page.evaluate(CONTRASTE_JS, ".botao[aria-disabled='true']") >= 4.5


def test_ata_de_outro_orgao_nao_tem_botao_do_proderj(page: Page, base_url):
    page.goto(f"{base_url}/ata/siga_rj/S1")
    expect(page.get_by_text("PRODERJ")).to_have_count(0)


def test_sem_erro_de_console_nem_de_csp(page: Page, base_url, erros_console):
    page.goto(f"{base_url}/?escopo=proderj")
    page.goto(f"{base_url}/ata/siga_rj/P2")
    assert erros_console == []
