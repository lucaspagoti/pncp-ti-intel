"""Avaliação da ordem da busca da web (ADR 0036): precisão@10 por consulta, antes e depois.

O juiz é independente da nota da busca: uma ata é relevante quando o item de **maior valor** dela
(quantidade × preço unitário) traz na cabeça as palavras de alguma alternativa da consulta (o termo
ou um sinônimo revisado), em singular ou plural; sem itens (busca PNCP), quando o começo do objeto
as traz. É um critério aproximado e o relatório lista o top 10 para conferência humana.

    uv run python -m pncp_ti.busca_avaliacao --antes --json antes.json   # no banco na 0010
    uv run python -m pncp_ti.busca_avaliacao --comparar antes.json        # no banco na 0011

Só lê o banco (papel `web_reader`).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from pncp_ti.config import get_settings, web_dsn
from pncp_ti.web import consultas, termos

RAIZ = Path(__file__).resolve().parents[2]
CONSULTAS = RAIZ / "evals" / "busca_consultas.csv"
TOPO = 10
INICIO_OBJETO = 80
# A ordem da 0010: radical do português sem peso, `ts_rank` sem normalização.
SQL_ANTES = (
    "SELECT fonte, id_ata, objeto FROM v_busca_atas "
    "WHERE documento @@ websearch_to_tsquery('portuguese', unaccent(%(q)s)) "
    "ORDER BY ts_rank(documento, websearch_to_tsquery('portuguese', unaccent(%(q)s))) DESC, "
    "fim ASC, id_ata LIMIT %(n)s"
)


def _cabeca(descricao: str | None, catalogo: str | None) -> str:
    if catalogo and catalogo.strip():
        return catalogo
    return re.split(r"\s+-\s+|[,;:]", descricao or "", maxsplit=1)[0]


def _casa(texto: str, alternativas: list[str]) -> bool:
    presentes = set(termos.palavras(texto))
    for frase in alternativas:
        palavras = termos.palavras(frase)
        if palavras and all(termos.variantes(p) & presentes for p in palavras):
            return True
    return False


async def _relevante(conn, fonte: str, id_ata: str, objeto: str, alternativas: list[str]) -> bool:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT descricao, nome_catalogo, COALESCE(quantidade, 1) * valor_unitario AS total "
            "FROM v_ata_itens_ti WHERE fonte = %s AND id_ata = %s "
            "ORDER BY total DESC NULLS LAST LIMIT 1",
            (fonte, id_ata),
        )
        principal = await cur.fetchone()
    if principal:
        return _casa(_cabeca(principal["descricao"], principal["nome_catalogo"]), alternativas)
    return _casa((objeto or "")[:INICIO_OBJETO], alternativas)


async def avaliar(conn, consultas_: list[str], antes: bool) -> dict[str, list[dict]]:
    resultado = {}
    for q in consultas_:
        if antes:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(SQL_ANTES, {"q": q, "n": TOPO})
                linhas = await cur.fetchall()
        else:
            linhas = (await consultas.buscar(conn, consultas.ler_filtros({"q": q}))).linhas[:TOPO]
        alts = [q, *termos.sinonimos(q)]
        resultado[q] = [
            {
                "fonte": linha["fonte"],
                "id_ata": linha["id_ata"],
                "objeto": linha["objeto"],
                "relevante": await _relevante(
                    conn, linha["fonte"], linha["id_ata"], linha["objeto"], alts
                ),
            }
            for linha in linhas
        ]
    return resultado


def _precisao(linhas: list[dict]) -> float:
    return sum(linha["relevante"] for linha in linhas) / TOPO


def relatorio(depois: dict[str, list[dict]], antes: dict[str, list[dict]] | None) -> str:
    linhas = [
        f"# Avaliação da busca da web — {date.today():%d/%m/%Y}",
        "",
        "Precisão@10 por consulta (ADR 0036). Relevante: o item de maior valor da ata traz o termo "
        "(ou um sinônimo revisado) na cabeça; sem itens, o começo do objeto. Critério aproximado: "
        "confira o top 10 abaixo.",
        "",
        "| Consulta | Antes | Depois |",
        "|---|---|---|",
    ]
    for q, top in depois.items():
        anterior = f"{_precisao(antes[q]):.0%}" if antes and q in antes else "—"
        linhas.append(f"| {q} | {anterior} | {_precisao(top):.0%} |")
    media = sum(_precisao(t) for t in depois.values()) / max(1, len(depois))
    media_antes = (
        f"{sum(_precisao(t) for t in antes.values()) / max(1, len(antes)):.0%}" if antes else "—"
    )
    linhas += [f"| **Média** | **{media_antes}** | **{media:.0%}** |", ""]
    for q, top in depois.items():
        linhas += [f"## {q}", ""]
        for n, item in enumerate(top, 1):
            marca = "✓" if item["relevante"] else "✗"
            objeto = " ".join((item["objeto"] or "").split())[:110].replace("|", "/")
            linhas.append(f"{n}. {marca} {objeto} (`{item['fonte']}`)")
        linhas.append("")
    return "\n".join(linhas)


async def principal(args: argparse.Namespace) -> int:
    with CONSULTAS.open(encoding="utf-8") as arquivo:
        lista = [linha["consulta"] for linha in csv.DictReader(arquivo)]
    async with await psycopg.AsyncConnection.connect(
        web_dsn(get_settings()), autocommit=True, options="-c default_transaction_read_only=on"
    ) as conn:
        resultado = await avaliar(conn, lista, args.antes)
    if args.json:
        args.json.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    if not args.antes:
        antes = json.loads(args.comparar.read_text(encoding="utf-8")) if args.comparar else None
        destino = RAIZ / "evals" / f"busca_{date.today():%Y%m%d}.md"
        destino.write_text(relatorio(resultado, antes), encoding="utf-8")
        print(destino)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--antes", action="store_true", help="ordem da 0010 (banco na 0010)")
    parser.add_argument("--json", type=Path, help="grava o resultado bruto")
    parser.add_argument("--comparar", type=Path, help="JSON do --antes para a coluna Antes")
    raise SystemExit(asyncio.run(principal(parser.parse_args())))


if __name__ == "__main__":
    main()
