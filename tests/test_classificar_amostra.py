"""Censo para rotulagem e avaliação de precisão/recall."""

import csv
from pathlib import Path

import pytest
import siga_dados as d

from pncp_ti.classificar.amostra import CABECALHO, escrever_csv, gerar_censo
from pncp_ti.classificar.avaliar import RotuloInvalido, avaliar, interpretar, relatorio
from pncp_ti.fontes.siga import arquivos_de_diretorio, carregar


def _linha(**campos):
    linha = {campo: "" for campo in CABECALHO}
    linha.update(campos)
    return linha


def test_escrever_csv_tem_cabecalho_e_nao_sobrescreve(tmp_path: Path):
    destino = tmp_path / "rotulagem.csv"
    escrever_csv([_linha(id_ata="1")], destino)
    assert destino.read_text(encoding="utf-8").splitlines()[0] == ",".join(CABECALHO)
    with pytest.raises(FileExistsError):
        escrever_csv([], destino)


@pytest.mark.parametrize("objeto", ["=1+1", "+SUM(1,2)", "-1+2", "@SUM(1,2)", "  =1+1", "\ttexto"])
def test_csv_exporta_formula_de_terceiro_como_texto(tmp_path, objeto):
    destino = tmp_path / "r.csv"
    escrever_csv([_linha(objeto=objeto, rotulo_lucas="TI")], destino)
    with destino.open(newline="", encoding="utf-8") as arquivo:
        exportada = next(csv.DictReader(arquivo))
    assert exportada["objeto"] == "'" + objeto
    assert exportada["rotulo_lucas"] == "TI"


async def test_censo_lista_todas_as_validas_vigentes_com_a_decisao_do_sistema(
    conn_ingest, tmp_path
):
    d.escrever(tmp_path, d.conjunto_basico())
    await carregar(conn_ingest, arquivos_de_diretorio(tmp_path))

    censo = await gerar_censo(conn_ingest)

    por_id = {linha["id_ata"]: linha for linha in censo}
    # Válida e vigente: 1, 2, 4, 6, 7 (3 é Interrompida, 5 venceu). Inclui as não-TI.
    assert set(por_id) == {"1", "2", "4", "6", "7"}
    assert por_id["1"]["filtro_sistema"] == "TI"
    assert por_id["2"]["filtro_sistema"] == "NAO_TI"
    assert por_id["6"]["filtro_sistema"] == "TI"
    assert "IMPRESSORA" not in por_id["1"]["nomes_catalogo"]  # só o nome de catálogo
    assert por_id["1"]["nomes_catalogo"].startswith("SERVICO DE LOCACAO")
    assert all(linha["rotulo_lucas"] == "" for linha in censo)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("TI", "TI"), (" sim ", "TI"), ("Não", "NAO_TI"), ("NAO_TI", "NAO_TI"), ("", None)],
)
def test_interpretar_rotulo(texto, esperado):
    assert interpretar(texto) == esperado


def test_rotulo_desconhecido_falha():
    with pytest.raises(RotuloInvalido):
        interpretar("talvez")


def test_avaliacao_calcula_precisao_recall_e_lista_erros():
    linhas = [
        _linha(id_ata="1", filtro_sistema="TI", rotulo_lucas="TI", rotulo_pre="TI"),
        _linha(id_ata="2", filtro_sistema="TI", rotulo_lucas="NAO_TI", rotulo_pre="TI"),
        _linha(id_ata="3", filtro_sistema="NAO_TI", rotulo_lucas="TI", rotulo_pre="TI"),
        _linha(id_ata="4", filtro_sistema="NAO_TI", rotulo_lucas="NAO_TI", rotulo_pre="NAO_TI"),
        _linha(id_ata="5", filtro_sistema="TI", rotulo_lucas="TI"),
        _linha(id_ata="6", filtro_sistema="NAO_TI", rotulo_lucas=""),
    ]
    av = avaliar(linhas)
    assert (av.verdadeiros_positivos, len(av.falsos_positivos), len(av.falsos_negativos)) == (
        2,
        1,
        1,
    )
    assert av.precisao == pytest.approx(2 / 3)
    assert av.recall == pytest.approx(2 / 3)
    assert av.sem_rotulo == 1
    assert av.concordancia_pre == (3, 4)
    texto = relatorio(av, Path("rotulagem.csv"), 0.85, 0.95)
    assert "| Precisão | 66.7% | ≥ 85% | não |" in texto
    assert "Falsos positivos" in texto and "| 2 |" in texto
