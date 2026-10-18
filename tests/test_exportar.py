"""Exportação CSV: texto de terceiros nunca vira fórmula e preços vêm das colunas certas."""

import csv
import io

from pncp_ti.web.exportar import CABECALHO, gerar_csv, neutralizar


def test_neutralizar_cobre_todos_os_gatilhos_de_formula():
    for perigoso in ("=1+1", "+1", "-1", "@SUM(A1)", "\rx", "\nx"):
        assert neutralizar(perigoso).startswith("'")


def test_gerar_csv_neutraliza_celulas_e_mapeia_colunas_de_preco():
    linha = {"fonte": "siga", "objeto": '=HYPERLINK("http://x")', "preco_min": 10, "preco_max": 20}
    linhas = list(csv.DictReader(io.StringIO(gerar_csv([linha]))))

    assert list(linhas[0]) == CABECALHO
    assert linhas[0]["objeto"].startswith("'=HYPERLINK")
    assert linhas[0]["preco_unitario_min"] == "10"
    assert linhas[0]["preco_unitario_max"] == "20"
    assert linhas[0]["uf"] == ""
