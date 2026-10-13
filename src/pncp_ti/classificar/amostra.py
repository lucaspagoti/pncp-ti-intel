"""Gera amostra de atas de TI candidatas e atas vigentes descartadas (ADR 0015)."""

from __future__ import annotations

import argparse
import asyncio
import csv
import random
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg

from pncp_ti.config import get_settings
from pncp_ti.db import conectar

CABECALHO = [
    "snapshot_id",
    "chave",
    "numero_controle_pncp_ata",
    "cnpj_orgao",
    "objeto_contratacao",
    "vigencia_inicio",
    "vigencia_fim",
    "filtro_sistema",
    "total_no_estrato",
    "amostra_no_estrato",
    "seed",
    "rotulo_lucas",
    "observacao",
]
CAMINHO_SAIDA = Path(__file__).resolve().parents[3] / "insumos" / "amostra_rotulada.csv"
N_CANDIDATAS = 100
TEXTOS_EXTERNOS = {"numero_controle_pncp_ata", "cnpj_orgao", "objeto_contratacao", "observacao"}


async def _candidatas(
    conn: psycopg.AsyncConnection, snapshot_id: Any
) -> AsyncIterator[dict[str, Any]]:
    async with conn.cursor(name=f"amostra_atas_{uuid4().hex}") as cursor:
        await cursor.execute(
            "SELECT a.chave_snapshot AS chave, a.numero_controle_pncp_ata, a.cnpj_orgao, "
            "a.objeto_contratacao, a.vigencia_inicio, a.vigencia_fim "
            "FROM atas a JOIN snapshots_atas_ti s ON s.id = a.snapshot_id "
            "WHERE s.id = %s AND s.status = 'concluido' ORDER BY a.chave_snapshot",
            (snapshot_id,),
        )
        async for linha in cursor:
            yield linha


async def gerar_amostra(conn: psycopg.AsyncConnection, *, seed: int = 0) -> list[dict[str, str]]:
    await conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    snapshot = await (
        await conn.execute(
            "SELECT id, candidatas_ti, descartadas, amostra_descartadas "
            "FROM snapshots_atas_ti WHERE ativo AND status = 'concluido'"
        )
    ).fetchone()
    if snapshot is None:
        return []

    rng = random.Random(seed)
    escolhidas: list[dict[str, Any]] = []
    vistas = 0
    async for linha in _candidatas(conn, snapshot["id"]):
        vistas += 1
        if len(escolhidas) < N_CANDIDATAS:
            escolhidas.append(linha)
        else:
            pos = rng.randrange(vistas)
            if pos < N_CANDIDATAS:
                escolhidas[pos] = linha

    descartadas_cursor = await conn.execute(
        "SELECT chave_snapshot AS chave, numero_controle_pncp_ata, cnpj_orgao, "
        "objeto_contratacao, vigencia_inicio, vigencia_fim "
        "FROM amostra_atas_descartadas WHERE snapshot_id = %s "
        "ORDER BY chave_snapshot",
        (snapshot["id"],),
    )
    descartadas = await descartadas_cursor.fetchall()
    if len(descartadas) > N_CANDIDATAS:
        descartadas = rng.sample(descartadas, k=N_CANDIDATAS)

    linhas: list[dict[str, str]] = []
    for tipo, amostra, total in (
        ("CANDIDATA_TI", escolhidas, snapshot["candidatas_ti"]),
        ("DESCARTADA", descartadas, snapshot["descartadas"]),
    ):
        for linha in amostra:
            linhas.append(
                {
                    "snapshot_id": str(snapshot["id"]),
                    "chave": linha["chave"],
                    "numero_controle_pncp_ata": linha["numero_controle_pncp_ata"],
                    "cnpj_orgao": linha["cnpj_orgao"] or "",
                    "objeto_contratacao": linha["objeto_contratacao"] or "",
                    "vigencia_inicio": str(linha["vigencia_inicio"] or ""),
                    "vigencia_fim": str(linha["vigencia_fim"] or ""),
                    "filtro_sistema": tipo,
                    "total_no_estrato": str(total),
                    "amostra_no_estrato": str(len(amostra)),
                    "seed": str(seed),
                    "rotulo_lucas": "",
                    "observacao": "",
                }
            )
    return linhas


def escrever_csv(amostra: list[dict[str, str]], caminho: Path = CAMINHO_SAIDA) -> None:
    with caminho.open("x", newline="", encoding="utf-8") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=CABECALHO)
        writer.writeheader()
        for linha in amostra:
            # Aspas do formato CSV não impedem planilhas de executar fórmulas.
            # Neutralizar somente texto externo; contagens/seed continuam numéricos.
            writer.writerow(
                {
                    campo: "'" + valor
                    if campo in TEXTOS_EXTERNOS
                    and (
                        valor.startswith(("\t", "\r", "\n"))
                        or valor.lstrip().startswith(("=", "+", "-", "@"))
                    )
                    else valor
                    for campo, valor in linha.items()
                }
            )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Amostra de atas candidatas e descartadas; preserva arquivos existentes."
    )
    parser.add_argument("--saida", type=Path, default=CAMINHO_SAIDA)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.saida.exists():
        raise SystemExit("Arquivo já existe. Use --saida com outro nome para preservar os rótulos.")
    conn = await conectar(get_settings())
    try:
        amostra = await gerar_amostra(conn, seed=args.seed)
    finally:
        await conn.close()
    if not amostra:
        raise SystemExit("Não há snapshot completo de atas; execute a ingestão diária primeiro.")
    escrever_csv(amostra, args.saida)
    print(f"{len(amostra)} linhas escritas em {args.saida}; seed={args.seed}")


if __name__ == "__main__":
    asyncio.run(main())
