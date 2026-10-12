"""Log de execução da ingestão (ADR 0005) — permite retomar sem reprocessar."""

from __future__ import annotations

import psycopg

from pncp_ti.ingest.windows import Janela


async def ja_concluida(
    conn: psycopg.AsyncConnection,
    entidade: str,
    modalidade_id: int | None,
    janela: Janela,
    pagina: int,
) -> bool:
    """True se essa combinação (entidade, modalidade, janela, página) já terminou `ok`."""
    row = await (
        await conn.execute(
            "SELECT 1 FROM log_execucao_ingestao "
            "WHERE entidade = %(entidade)s "
            "AND coalesce(modalidade_id, -1) = coalesce(%(modalidade_id)s, -1) "
            "AND janela_inicio = %(inicio)s AND janela_fim = %(fim)s "
            "AND pagina = %(pagina)s AND status = 'ok'",
            {
                "entidade": entidade,
                "modalidade_id": modalidade_id,
                "inicio": janela.inicio,
                "fim": janela.fim,
                "pagina": pagina,
            },
        )
    ).fetchone()
    return row is not None


async def registrar(
    conn: psycopg.AsyncConnection,
    *,
    entidade: str,
    modalidade_id: int | None,
    janela: Janela,
    pagina: int,
    registros_lidos: int,
    registros_gravados: int,
    falhas: int,
    status: str,
    erro_mensagem: str | None = None,
) -> None:
    # `ON CONFLICT` contra o índice único parcial `ux_log_execucao_combo`
    # (migração 0001): sem isso, reprocessar com `--forcar` uma página já
    # marcada `ok` bate duas vezes na mesma chave e sobe `UniqueViolation`.
    # Usar `ON CONFLICT` em vez de `DELETE`+`INSERT` evita precisar conceder
    # `DELETE` ao papel `ingest` (que só tem INSERT/UPDATE/SELECT) só pra isso.
    await conn.execute(
        "INSERT INTO log_execucao_ingestao "
        "(entidade, modalidade_id, janela_inicio, janela_fim, pagina, "
        " registros_lidos, registros_gravados, falhas, status, erro_mensagem, concluido_em) "
        "VALUES (%(entidade)s, %(modalidade_id)s, %(inicio)s, %(fim)s, %(pagina)s, "
        " %(lidos)s, %(gravados)s, %(falhas)s, %(status)s, %(erro)s, now()) "
        "ON CONFLICT (entidade, (coalesce(modalidade_id, -1)), janela_inicio, janela_fim, pagina) "
        "WHERE status = 'ok' "
        "DO UPDATE SET "
        " registros_lidos = excluded.registros_lidos, "
        " registros_gravados = excluded.registros_gravados, "
        " falhas = excluded.falhas, "
        " status = excluded.status, "
        " erro_mensagem = excluded.erro_mensagem, "
        " concluido_em = excluded.concluido_em",
        {
            "entidade": entidade,
            "modalidade_id": modalidade_id,
            "inicio": janela.inicio,
            "fim": janela.fim,
            "pagina": pagina,
            "lidos": registros_lidos,
            "gravados": registros_gravados,
            "falhas": falhas,
            "status": status,
            "erro": erro_mensagem,
        },
    )
