"""Aplicação FastAPI da web local (R4, ADR 0018): só leitura, só views, só `127.0.0.1`."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg_pool import AsyncConnectionPool, PoolTimeout
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pncp_ti.config import get_settings, web_dsn
from pncp_ti.web import consultas
from pncp_ti.web.exportar import CABECALHO_ITENS, gerar_csv

BASE = Path(__file__).parent
HOSTS_PADRAO = "127.0.0.1,localhost,testserver"
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
CABECALHOS_SEGURANCA = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
OPCOES_CONEXAO = "-c default_transaction_read_only=on -c statement_timeout=8000"


def _brl(valor: Decimal | None) -> str:
    if valor is None:
        return "—"
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "#").replace(".", ",").replace("#", ".")


def _data(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


def _numero(valor: Decimal | None) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.2f}".rstrip("0").rstrip(".").replace(",", ".")


def _url_segura(valor: str | None) -> str:
    """Só http(s) vira link; texto de terceiros nunca vira `javascript:`."""
    return valor if valor and valor.startswith(("https://", "http://")) else ""


async def conexao(request: Request) -> AsyncIterator[psycopg.AsyncConnection]:
    async with request.app.state.pool.connection() as conn:
        yield conn


Conn = Annotated[psycopg.AsyncConnection, Depends(conexao)]


def criar_app(dsn: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def ciclo(_: FastAPI) -> AsyncIterator[None]:
        pool = AsyncConnectionPool(
            dsn or web_dsn(get_settings()),
            min_size=1,
            max_size=4,
            # Conexão morta (Postgres reiniciado) é descartada antes de ir para a requisição.
            check=AsyncConnectionPool.check_connection,
            kwargs={"options": OPCOES_CONEXAO, "autocommit": True},
            open=False,
        )
        await pool.open()
        app.state.pool = pool
        try:
            yield
        finally:
            await pool.close()

    app = FastAPI(title="pncp-ti", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo)
    hosts = [h.strip() for h in os.environ.get("WEB_ALLOWED_HOSTS", HOSTS_PADRAO).split(",") if h]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    templates = Jinja2Templates(directory=BASE / "templates")
    templates.env.autoescape = True
    templates.env.filters.update(
        brl=_brl,
        data=_data,
        numero=_numero,
        url_segura=_url_segura,
        preco_br=consultas.como_texto,
        dias_restantes=consultas.dias_restantes,
    )
    templates.env.globals.update(FONTES=consultas.FONTES, ESFERAS=consultas.ESFERAS)

    @app.middleware("http")
    async def seguranca(request: Request, call_next):
        resposta = await call_next(request)
        for nome, valor in CABECALHOS_SEGURANCA.items():
            resposta.headers.setdefault(nome, valor)
        return resposta

    def _qs(filtros: consultas.Filtros, **extra: str | int) -> str:
        return urlencode({**filtros.como_dict(), **{k: str(v) for k, v in extra.items()}})

    templates.env.globals["qs"] = _qs

    @app.get("/saude", response_class=PlainTextResponse)
    async def saude(request: Request) -> Response:
        try:
            async with request.app.state.pool.connection(timeout=5) as conn:
                await conn.execute("SELECT 1 FROM v_cargas_web LIMIT 1")
        except (psycopg.Error, PoolTimeout):
            return PlainTextResponse("banco indisponível", status_code=503)
        return PlainTextResponse("ok")

    @app.get("/", response_class=HTMLResponse)
    async def inicio(request: Request, conn: Conn) -> Response:
        filtros = consultas.ler_filtros(request.query_params)
        pagina = await consultas.buscar(conn, filtros)
        contexto = {
            "f": filtros,
            "p": pagina,
            "opcoes": await consultas.opcoes_filtro(conn),
            "facetas": await consultas.facetas(conn, filtros),
            "ativos": consultas.filtros_ativos(filtros),
            "cargas": await consultas.cargas(conn),
            "ordens": list(consultas.ORDENS),
        }
        # HTMX pede só o bloco de resultados.
        modelo = "_resultados.html" if request.headers.get("HX-Request") else "index.html"
        return templates.TemplateResponse(request, modelo, contexto)

    @app.get("/ata/{fonte}/{id_ata:path}/itens.csv")
    async def exportar_itens(fonte: str, id_ata: str, conn: Conn) -> Response:
        if fonte not in consultas.FONTES or len(id_ata) > 200:
            raise HTTPException(404)
        if await consultas.ata(conn, fonte, id_ata) is None:
            raise HTTPException(404)
        linhas = await consultas.itens(conn, fonte, id_ata, limite=None)
        return Response(
            gerar_csv(linhas, CABECALHO_ITENS),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="itens_ata.csv"'},
        )

    @app.get("/ata/{fonte}/{id_ata:path}", response_class=HTMLResponse)
    async def detalhe(request: Request, fonte: str, id_ata: str, conn: Conn) -> Response:
        if fonte not in consultas.FONTES or len(id_ata) > 200:
            raise HTTPException(404)
        registro = await consultas.ata(conn, fonte, id_ata)
        if registro is None:
            raise HTTPException(404)
        contexto = {
            "a": registro,
            "itens": await consultas.itens(conn, fonte, id_ata),
            "consumo": await consultas.consumo(conn, fonte, id_ata),
            "cargas": await consultas.cargas(conn),
        }
        return templates.TemplateResponse(request, "ata.html", contexto)

    @app.get("/exportar.csv")
    async def exportar(request: Request, conn: Conn) -> Response:
        filtros = consultas.ler_filtros(request.query_params)
        linhas = await consultas.para_exportar(conn, filtros)
        return Response(
            gerar_csv(linhas),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="atas_ti_vigentes.csv"'},
        )

    return app


def app_padrao() -> FastAPI:
    return criar_app()


def main() -> None:
    import uvicorn

    porta = int(os.environ.get("WEB_PORT", "8000"))
    uvicorn.run(
        "pncp_ti.web.app:app_padrao", factory=True, host="127.0.0.1", port=porta, log_level="info"
    )


if __name__ == "__main__":
    main()
