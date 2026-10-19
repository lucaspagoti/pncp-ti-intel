"""Exportação CSV pelo botão: cabeçalho e fórmula neutralizada."""

from __future__ import annotations

import csv

import web_dados
from playwright.sync_api import Page

from pncp_ti.web.exportar import CABECALHO


def test_exportar_csv_neutraliza_formula(page: Page, base_url, tmp_path):
    page.goto(f"{base_url}/?q=toner")
    with page.expect_download() as download:
        page.get_by_role("link", name="Exportar CSV").click()
    assert download.value.suggested_filename == "atas_ti_vigentes.csv"
    caminho = tmp_path / "atas.csv"
    download.value.save_as(caminho)
    linhas = list(csv.reader(caminho.open(encoding="utf-8-sig")))
    assert linhas[0] == CABECALHO
    objetos = [linha[CABECALHO.index("objeto")] for linha in linhas[1:]]
    assert objetos == ["'" + web_dados.OBJETO_FORMULA]
