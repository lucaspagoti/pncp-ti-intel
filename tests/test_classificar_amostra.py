"""Amostra de atas candidatas e rejeitadas para rotulagem manual."""

from pathlib import Path
from uuid import uuid4

import pytest

from pncp_ti.classificar.amostra import CABECALHO, escrever_csv, gerar_amostra
from pncp_ti.db import upsert
from pncp_ti.ingest.mapeadores import mapear_ata


def _ata(controle: str, objeto: str) -> dict:
    return {
        "numeroControlePNCPAta": controle,
        "objetoContratacao": objeto,
        "cancelado": False,
        "vigenciaInicio": "2026-01-01",
        "vigenciaFim": "2026-12-31",
    }


async def test_amostra_identifica_candidatas_e_descartadas(conn_ingest):
    snapshot = uuid4()
    await conn_ingest.execute(
        "INSERT INTO snapshots_atas_ti "
        "(id, data_referencia, status, ativo, candidatas_ti, descartadas, amostra_descartadas) "
        "VALUES (%s, '2026-10-12', 'concluido', true, 1, 1, 1)",
        (snapshot,),
    )
    ata_ti = mapear_ata(_ata("ata-ti", "Aquisição de computadores"))
    ata_ti.update(snapshot_id=snapshot, chave_snapshot=f"{snapshot}:ata-ti")
    await upsert(conn_ingest, "atas", "chave_snapshot", ata_ti)
    await conn_ingest.execute(
        "INSERT INTO amostra_atas_descartadas "
        "(chave_snapshot, snapshot_id, numero_controle_pncp_ata, objeto_contratacao) "
        "VALUES (%s, %s, %s, %s)",
        (f"{snapshot}:ata-geral", snapshot, "ata-geral", "Mobiliário escolar"),
    )
    await conn_ingest.commit()

    linhas = await gerar_amostra(conn_ingest, seed=42)

    assert {linha["filtro_sistema"] for linha in linhas} == {"CANDIDATA_TI", "DESCARTADA"}
    assert {linha["numero_controle_pncp_ata"] for linha in linhas} == {"ata-ti", "ata-geral"}
    assert {linha["total_no_estrato"] for linha in linhas} == {"1"}


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


async def test_amostra_limitada_reprodutivel_e_com_pesos_corretos(conn_ingest):
    from datetime import date

    from pncp_ti.ingest.atas import ingerir_snapshot
    from pncp_ti.ingest.rate_limit import LimitadorTaxa

    registros = [_ata(f"ti-{i}", "Computadores") for i in range(250)]
    registros += [_ata(f"geral-{i}", "Mobiliário") for i in range(400)]

    class Cliente:
        async def list_resource(self, _path, **_kwargs):
            return {"data": registros, "totalPaginas": 1}

    await ingerir_snapshot(conn_ingest, Cliente(), LimitadorTaxa(10_000), date(2026, 10, 12))
    primeira = await gerar_amostra(conn_ingest, seed=42)
    await conn_ingest.rollback()
    segunda = await gerar_amostra(conn_ingest, seed=42)
    assert primeira == segunda
    assert len(primeira) == len({r["chave"] for r in primeira}) == 200
    for estrato, total in (("CANDIDATA_TI", "250"), ("DESCARTADA", "400")):
        linhas = [r for r in primeira if r["filtro_sistema"] == estrato]
        assert len(linhas) == 100
        assert {r["total_no_estrato"] for r in linhas} == {total}
        assert {r["amostra_no_estrato"] for r in linhas} == {"100"}
