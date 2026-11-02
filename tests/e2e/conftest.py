"""E2E da web (W0, ADR 0029): Chromium do Playwright contra um uvicorn real no banco de teste.

Só rodam com `PNCP_TI_E2E=1` (`make e2e`); no `make test` ficam como pulados.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from dataclasses import replace
from datetime import date, timedelta
from uuid import uuid4

import psycopg
import pytest
import uvicorn
import web_dados

from pncp_ti.config import get_settings, ingest_dsn, web_dsn
from pncp_ti.web.app import criar_app

ATAS_PAGINACAO = 30  # mais que TAMANHO_PAGINA (20)
DESKTOP = {"width": 1366, "height": 768}
CELULAR = {"width": 390, "height": 844}


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PNCP_TI_E2E") == "1":
        return
    pular = pytest.mark.skip(reason="E2E só com PNCP_TI_E2E=1 (make e2e)")
    for item in items:
        if "tests/e2e/" in item.nodeid:
            item.add_marker(pular)


def _semear(dsn: str) -> None:
    arp = uuid4()
    comandos = web_dados.comandos(arp=arp)
    comandos.append(
        web_dados.ata(arp, "F1", web_dados.OBJETO_FORMULA, fim=date.today() + timedelta(days=200))
    )
    comandos += [
        web_dados.ata(arp, f"P{n:02}", f"Cabo de rede lote {n:02}") for n in range(ATAS_PAGINACAO)
    ]
    # QA-001: objeto e órgão sem espaço, que não podem alargar a página.
    longo = "zzzlongo " + "X" * 250
    comandos.append(web_dados.ata(arp, "LONGO", longo, orgao="O" * 200))
    with psycopg.connect(dsn) as conn:
        conn.execute("DELETE FROM cargas")
        for comando, parametros in comandos:
            conn.execute(comando, parametros)
        conn.execute("SELECT atualizar_busca()")


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(nome_banco_teste):
    """URL de um uvicorn em thread, servindo a web com o papel `web_reader`."""
    if os.environ.get("PNCP_TI_E2E") != "1":
        pytest.skip("E2E só com PNCP_TI_E2E=1")
    configuracao = replace(get_settings(), postgres_db=nome_banco_teste)
    _semear(ingest_dsn(configuracao))
    porta = _porta_livre()
    servidor = uvicorn.Server(
        uvicorn.Config(
            criar_app(web_dsn(configuracao)), host="127.0.0.1", port=porta, log_level="warning"
        )
    )
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("uvicorn do E2E não subiu")
    yield f"http://127.0.0.1:{porta}"
    servidor.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Desktop de referência da W2 (1366); os testes de celular trocam para 390."""
    return {**browser_context_args, "viewport": DESKTOP}


@pytest.fixture
def erros_console(page):
    """Erros de console e de página (inclui violação de CSP) durante o teste."""
    erros: list[str] = []
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(str(e)))
    return erros
