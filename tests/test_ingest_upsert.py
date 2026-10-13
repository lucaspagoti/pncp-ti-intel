"""Snapshot idempotente e publicação atômica das atas de TI."""

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest
from compras_mcp.errors import ComprasHTTPError
from psycopg.rows import dict_row

from pncp_ti.config import get_settings, ingest_dsn
from pncp_ti.ingest.atas import ingerir_snapshot
from pncp_ti.ingest.executar import FalhasIngestao
from pncp_ti.ingest.rate_limit import LimitadorTaxa

REFERENCIA = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

ATA_TI = {
    "numeroControlePNCPAta": "ata-sintetica-ti",
    "numeroControlePNCPCompra": "compra-sintetica-ti",
    "objetoContratacao": "Aquisição de computadores",
    "cancelado": False,
    "vigenciaInicio": REFERENCIA.isoformat(),
    "vigenciaFim": REFERENCIA.isoformat(),
}
ATA_DESCARTADA = {
    "numeroControlePNCPAta": "ata-sintetica-geral",
    "numeroControlePNCPCompra": "compra-sintetica-geral",
    "objetoContratacao": "Aquisição de mobiliário escolar",
    "cancelado": False,
    "vigenciaInicio": REFERENCIA.isoformat(),
    "vigenciaFim": REFERENCIA.isoformat(),
}


class ClienteFalso:
    def __init__(self, registros=None, erro=None):
        self.registros = registros or []
        self.erro = erro

    async def list_resource(self, _path, *, pagina, **_kwargs):
        if self.erro:
            raise self.erro
        return {"data": self.registros if pagina == 1 else [], "totalPaginas": 1}


async def test_snapshot_publica_candidatas_e_amostra_de_rejeitadas(conn_ingest, conn_reader):
    cliente = ClienteFalso([ATA_TI, ATA_DESCARTADA])
    for _ in range(2):
        await ingerir_snapshot(conn_ingest, cliente, LimitadorTaxa(10_000), REFERENCIA)

    atual = await (
        await conn_ingest.execute(
            "SELECT id, registros_lidos, candidatas_ti, descartadas, amostra_descartadas "
            "FROM snapshots_atas_ti WHERE ativo AND status = 'concluido'"
        )
    ).fetchone()
    candidatas = await (
        await conn_reader.execute("SELECT numero_controle_pncp_ata FROM v_atas_ti_vigentes")
    ).fetchall()
    rejeitadas = await (
        await conn_ingest.execute(
            "SELECT numero_controle_pncp_ata FROM amostra_atas_descartadas WHERE snapshot_id = %s",
            (atual["id"],),
        )
    ).fetchall()
    historico = await (
        await conn_ingest.execute("SELECT count(*) AS n FROM snapshots_atas_ti")
    ).fetchone()

    assert (atual["registros_lidos"], atual["candidatas_ti"], atual["descartadas"]) == (2, 1, 1)
    assert atual["amostra_descartadas"] == 1
    assert [row["numero_controle_pncp_ata"] for row in candidatas] == [
        ATA_TI["numeroControlePNCPAta"]
    ]
    assert [row["numero_controle_pncp_ata"] for row in rejeitadas] == [
        ATA_DESCARTADA["numeroControlePNCPAta"]
    ]
    assert historico["n"] == 1


async def test_snapshot_deduplica_ata_repetida_entre_paginas(conn_ingest):
    cliente = ClientePaginas(
        [
            {"data": [ATA_TI, ATA_DESCARTADA], "totalPaginas": 2},
            {"data": [ATA_TI, ATA_DESCARTADA], "totalPaginas": 2},
        ]
    )
    await ingerir_snapshot(conn_ingest, cliente, LimitadorTaxa(10_000), REFERENCIA)

    snapshot = await (
        await conn_ingest.execute(
            "SELECT registros_lidos, candidatas_ti, descartadas, amostra_descartadas "
            "FROM snapshots_atas_ti WHERE ativo"
        )
    ).fetchone()
    amostra = await (
        await conn_ingest.execute("SELECT count(*) AS n FROM amostra_atas_descartadas")
    ).fetchone()

    assert (snapshot["registros_lidos"], snapshot["candidatas_ti"], snapshot["descartadas"]) == (
        2,
        1,
        1,
    )
    assert snapshot["amostra_descartadas"] == amostra["n"] == 1


async def test_falha_nao_substitui_o_ultimo_snapshot_concluido(conn_ingest, conn_reader):
    await ingerir_snapshot(
        conn_ingest,
        ClienteFalso([ATA_TI]),
        LimitadorTaxa(10_000),
        REFERENCIA,
    )
    with pytest.raises(ValueError):
        await ingerir_snapshot(
            conn_ingest,
            ClienteFalso(erro=ValueError("fonte indisponível")),
            LimitadorTaxa(10_000),
            REFERENCIA,
        )

    linha = await (
        await conn_reader.execute("SELECT numero_controle_pncp_ata FROM v_atas_ti_vigentes")
    ).fetchone()
    status = await (
        await conn_ingest.execute(
            "SELECT count(*) AS n FROM snapshots_atas_ti WHERE status = 'falhou'"
        )
    ).fetchone()
    assert linha["numero_controle_pncp_ata"] == ATA_TI["numeroControlePNCPAta"]
    assert status["n"] == 1


class ClientePaginas:
    def __init__(self, paginas):
        self.paginas = paginas

    async def list_resource(self, _path, *, pagina, **_kwargs):
        resposta = self.paginas[pagina - 1]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


async def test_204_no_meio_da_carga_nao_publica_snapshot_parcial(conn_ingest, conn_reader):
    await ingerir_snapshot(conn_ingest, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA)
    nova = {**ATA_TI, "numeroControlePNCPAta": "ata-parcial"}
    cliente = ClientePaginas(
        [
            {"data": [nova], "totalPaginas": 3},
            ComprasHTTPError("Resposta nao-JSON de pncp/v1/atas: "),
        ]
    )
    with pytest.raises(ValueError):
        await ingerir_snapshot(conn_ingest, cliente, LimitadorTaxa(10_000), REFERENCIA)
    linhas = await (
        await conn_reader.execute("SELECT numero_controle_pncp_ata FROM v_atas_ti_vigentes")
    ).fetchall()
    assert [row["numero_controle_pncp_ata"] for row in linhas] == [ATA_TI["numeroControlePNCPAta"]]


async def test_erro_sql_na_amostra_limpa_staging_e_libera_lock(conn_ingest, conn_reader):
    from dataclasses import replace

    await ingerir_snapshot(conn_ingest, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA)
    descartada_invalida = {**ATA_DESCARTADA, "cnpjOrgao": "1" * 15}
    with pytest.raises(psycopg.errors.StringDataRightTruncation):
        await ingerir_snapshot(
            conn_ingest,
            ClienteFalso([ATA_TI, descartada_invalida]),
            LimitadorTaxa(10_000),
            REFERENCIA,
        )
    falhou = await (
        await conn_ingest.execute("SELECT id FROM snapshots_atas_ti WHERE status = 'falhou'")
    ).fetchone()
    assert falhou is not None
    assert (
        await (
            await conn_ingest.execute(
                "SELECT count(*) AS n FROM atas WHERE snapshot_id = %s", (falhou["id"],)
            )
        ).fetchone()
    )["n"] == 0
    assert (
        await (await conn_reader.execute("SELECT count(*) AS n FROM v_atas_ti_vigentes")).fetchone()
    )["n"] == 1
    settings = replace(get_settings(), postgres_db=conn_ingest.info.dbname)
    async with await psycopg.AsyncConnection.connect(
        ingest_dsn(settings), row_factory=dict_row
    ) as outra:
        await ingerir_snapshot(outra, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA)


async def test_publicacao_atomica_e_exclusao_mutua(conn_ingest, conn_reader):
    await ingerir_snapshot(conn_ingest, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA)
    novas = [{**ATA_TI, "numeroControlePNCPAta": f"ata-nova-{i}"} for i in (1, 2)]
    settings = replace(get_settings(), postgres_db=conn_ingest.info.dbname)
    # A consulta permanece correta mesmo numa sessão com outro fuso.
    await conn_reader.execute("SET TIME ZONE 'Pacific/Kiritimati'")

    class ClienteObservado:
        async def list_resource(self, _path, *, pagina, **_kwargs):
            if pagina == 2:
                visiveis = await (
                    await conn_reader.execute(
                        "SELECT numero_controle_pncp_ata FROM v_atas_ti_vigentes"
                    )
                ).fetchall()
                assert [r["numero_controle_pncp_ata"] for r in visiveis] == [
                    ATA_TI["numeroControlePNCPAta"]
                ]
                staging = await (
                    await conn_ingest.execute(
                        "SELECT count(*) AS n FROM atas a JOIN snapshots_atas_ti s "
                        "ON s.id = a.snapshot_id WHERE s.status = 'em_andamento'"
                    )
                ).fetchone()
                assert staging["n"] == 1
                async with await psycopg.AsyncConnection.connect(
                    ingest_dsn(settings), row_factory=dict_row
                ) as outra:
                    with pytest.raises(RuntimeError, match="já existe"):
                        await ingerir_snapshot(
                            outra, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA
                        )
            return {"data": [novas[pagina - 1]], "totalPaginas": 2}

    await ingerir_snapshot(conn_ingest, ClienteObservado(), LimitadorTaxa(10_000), REFERENCIA)
    visiveis = await (
        await conn_reader.execute(
            "SELECT numero_controle_pncp_ata FROM v_atas_ti_vigentes ORDER BY 1"
        )
    ).fetchall()
    assert [r["numero_controle_pncp_ata"] for r in visiveis] == [
        r["numeroControlePNCPAta"] for r in novas
    ]


@pytest.mark.parametrize("registros", [[], [{"objetoContratacao": "sem identificador"}]])
async def test_carga_vazia_ou_malformada_preserva_anterior(conn_ingest, conn_reader, registros):
    await ingerir_snapshot(conn_ingest, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA)
    with pytest.raises((ValueError, FalhasIngestao)):
        await ingerir_snapshot(
            conn_ingest, ClienteFalso(registros), LimitadorTaxa(10_000), REFERENCIA
        )
    assert (
        await (await conn_reader.execute("SELECT count(*) AS n FROM v_atas_ti_vigentes")).fetchone()
    )["n"] == 1


async def test_vigencia_cancelamento_e_reclassificacao(conn_ingest, conn_reader):
    await ingerir_snapshot(conn_ingest, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA)
    registros = [
        {**ATA_TI, "objetoContratacao": "Objeto corrigido: mobiliário"},
        {**ATA_TI, "numeroControlePNCPAta": "cancelada", "cancelado": True},
        {
            **ATA_TI,
            "numeroControlePNCPAta": "vencida",
            "vigenciaFim": (REFERENCIA - timedelta(days=1)).isoformat(),
        },
        {
            **ATA_TI,
            "numeroControlePNCPAta": "futura",
            "vigenciaInicio": (REFERENCIA + timedelta(days=1)).isoformat(),
        },
    ]
    await ingerir_snapshot(conn_ingest, ClienteFalso(registros), LimitadorTaxa(10_000), REFERENCIA)
    assert (
        await (await conn_reader.execute("SELECT count(*) AS n FROM v_atas_ti_vigentes")).fetchone()
    )["n"] == 0
    descartadas = await (
        await conn_ingest.execute("SELECT numero_controle_pncp_ata FROM amostra_atas_descartadas")
    ).fetchall()
    assert [r["numero_controle_pncp_ata"] for r in descartadas] == [ATA_TI["numeroControlePNCPAta"]]


async def test_total_reduzido_nao_encerra_carga_antes_da_pagina_prometida(conn_ingest):
    novas = [{**ATA_TI, "numeroControlePNCPAta": f"ata-total-{i}"} for i in (1, 2, 3)]
    cliente = ClientePaginas(
        [
            {"data": [novas[0]], "totalPaginas": 3},
            {"data": [novas[1]], "totalPaginas": 2},
            {"data": [novas[2]], "totalPaginas": 3},
        ]
    )
    await ingerir_snapshot(conn_ingest, cliente, LimitadorTaxa(10_000), REFERENCIA)
    assert (
        await (
            await conn_ingest.execute("SELECT candidatas_ti FROM snapshots_atas_ti WHERE ativo")
        ).fetchone()
    )["candidatas_ti"] == 3


async def test_erro_durante_troca_do_snapshot_reverte_publicacao(
    conn_ingest, conn_reader, monkeypatch
):
    await ingerir_snapshot(conn_ingest, ClienteFalso([ATA_TI]), LimitadorTaxa(10_000), REFERENCIA)
    execute = conn_ingest.execute

    async def falha_na_remocao(query, *args, **kwargs):
        if isinstance(query, str) and query.startswith("DELETE FROM snapshots_atas_ti"):
            return await execute("SELECT 1 / 0")
        return await execute(query, *args, **kwargs)

    monkeypatch.setattr(conn_ingest, "execute", falha_na_remocao)
    nova = {**ATA_TI, "numeroControlePNCPAta": "ata-ainda-nao-publicada"}
    with pytest.raises(psycopg.errors.DivisionByZero):
        await ingerir_snapshot(conn_ingest, ClienteFalso([nova]), LimitadorTaxa(10_000), REFERENCIA)
    linhas = await (
        await conn_reader.execute("SELECT numero_controle_pncp_ata FROM v_atas_ti_vigentes")
    ).fetchall()
    assert [r["numero_controle_pncp_ata"] for r in linhas] == [ATA_TI["numeroControlePNCPAta"]]
    assert (await (await conn_ingest.execute("SELECT count(*) AS n FROM atas")).fetchone())[
        "n"
    ] == 1
