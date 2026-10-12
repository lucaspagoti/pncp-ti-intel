"""Conexão com o Postgres e upsert genérico para a camada de ingestão.

Toda escrita usa o papel `ingest` (só INSERT/UPDATE/SELECT nas tabelas base — a
migração `0001_f1_base_historica` cria o papel e os grants; `mcp_reader` só lê as
views `v_*`, sem acesso às tabelas base nem à coluna `raw`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row

from pncp_ti.config import Settings, ingest_dsn


async def conectar(settings: Settings) -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(ingest_dsn(settings), row_factory=dict_row)


async def upsert(
    conn: psycopg.AsyncConnection,
    tabela: str,
    chave: str,
    valores: Mapping[str, Any],
) -> None:
    """UPSERT por chave natural única — ingestão idempotente (ADR 0005).

    `tabela` e `chave` são sempre constantes do próprio código de ingestão, nunca
    entrada externa — não há risco de injeção por aqui (diferente de uma tool MCP
    exposta a um agente, que é a situação que a regra de "nenhuma tool com SQL
    livre" do CLAUDE.md cobre).
    """
    colunas = list(valores.keys())
    placeholders = [f"%({c})s" for c in colunas]
    # Órgãos chegam com completude distinta; NULL/ausência não apaga metadado conhecido.
    atualizacoes = [
        f"{c} = COALESCE(EXCLUDED.{c}, {tabela}.{c})"
        if tabela == "orgaos"
        else f"{c} = EXCLUDED.{c}"
        for c in colunas
        if c != chave
    ]
    acao_conflito = f"DO UPDATE SET {', '.join(atualizacoes)}" if atualizacoes else "DO NOTHING"
    sql = (
        f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT ({chave}) {acao_conflito}"
    )
    await conn.execute(sql, dict(valores))
