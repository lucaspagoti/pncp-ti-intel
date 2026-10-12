"""CLI de ingestão — `make ingest` (diário) e `make ingest-backfill` (histórico)."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta

import structlog

from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.ingest import atas, contratacoes, contratos
from pncp_ti.ingest.client import criar_cliente
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import gerar_janelas

log = structlog.get_logger(__name__)

ADAPTADORES = {
    "contratacoes": contratacoes.ingerir,
    "atas": atas.ingerir,
    "contratos": contratos.ingerir,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingestão do pncp-ti (Fase 1).")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--diario", action="store_true", help="janela de ontem até hoje.")
    modo.add_argument("--backfill", action="store_true", help="de --desde até hoje.")
    parser.add_argument("--desde", type=date.fromisoformat, default=None)
    parser.add_argument(
        "--entidades",
        default="contratacoes,atas,contratos",
        help="lista separada por vírgula (default: todas).",
    )
    parser.add_argument(
        "--forcar", action="store_true", help="reprocessa mesmo o que já está marcado ok."
    )
    return parser.parse_args()


async def _rodar(entidades: list[str], desde: date, ate: date, forcar: bool) -> None:
    settings = get_settings()
    limitador = LimitadorTaxa(settings.requests_per_second)
    janelas = gerar_janelas(desde, ate)
    conn = await conectar(settings)
    try:
        async with criar_cliente() as cliente:
            for nome in entidades:
                adaptador = ADAPTADORES[nome]
                for janela in janelas:
                    log.info("ingest.janela_iniciada", entidade=nome, janela=str(janela))
                    await adaptador(conn, cliente, limitador, janela, forcar=forcar)
    finally:
        await conn.close()


def main() -> None:
    args = _parse_args()
    entidades = [e.strip() for e in args.entidades.split(",") if e.strip()]
    for nome in entidades:
        if nome not in ADAPTADORES:
            raise SystemExit(f"entidade desconhecida: {nome!r} (opções: {sorted(ADAPTADORES)})")

    hoje = date.today()
    if args.diario:
        desde, ate = hoje - timedelta(days=1), hoje
    else:
        desde = args.desde if args.desde is not None else get_settings().backfill_start
        ate = hoje

    asyncio.run(_rodar(entidades, desde, ate, args.forcar))


if __name__ == "__main__":
    main()
