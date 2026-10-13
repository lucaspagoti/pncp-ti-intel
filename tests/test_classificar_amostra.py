"""Amostra de atas candidatas e rejeitadas para rotulagem manual."""

from pathlib import Path

import pytest

from pncp_ti.classificar.amostra import CABECALHO, escrever_csv


def test_escrever_csv_tem_cabecalho_e_nao_sobrescreve(tmp_path: Path):
    destino = tmp_path / "amostra.csv"
    linha = {campo: "" for campo in CABECALHO}
    linha["numero_controle_pncp_ata"] = "ata-1"
    escrever_csv([linha], destino)
    assert destino.read_text(encoding="utf-8").splitlines()[0] == ",".join(CABECALHO)
    with pytest.raises(FileExistsError):
        escrever_csv([], destino)
    assert "ata-1" in destino.read_text(encoding="utf-8")


@pytest.mark.parametrize("objeto", ["=1+1", "+SUM(1,2)", "-1+2", "@SUM(1,2)", "  =1+1", "\ttexto"])
def test_csv_exporta_formula_de_terceiro_como_texto(tmp_path, objeto):
    import csv

    linha = {campo: "" for campo in CABECALHO}
    linha.update(objeto_contratacao=objeto, seed="-1", total_no_estrato="1000")
    destino = tmp_path / "amostra.csv"
    escrever_csv([linha], destino)
    with destino.open(newline="", encoding="utf-8") as arquivo:
        exportada = next(csv.DictReader(arquivo))
    assert exportada["objeto_contratacao"] == "'" + objeto
    assert exportada["seed"] == "-1"
    assert exportada["total_no_estrato"] == "1000"
    assert linha["objeto_contratacao"] == objeto
