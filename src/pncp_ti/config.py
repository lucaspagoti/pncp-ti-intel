"""Configuração da camada de ingestão, carregada do `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo
from sqlalchemy import URL


def _find_dotenv() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return Path(".env")


load_dotenv(_find_dotenv(), interpolate=False)


@dataclass(frozen=True, slots=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_admin_password: str | None
    ingest_password: str | None
    reader_password: str | None
    web_password: str | None
    requests_per_second: float
    arp_requests_per_second: float
    arp_max_requisicoes: int
    arp_varredura_minutos: float


def exigir(valor: str | None, nome: str) -> str:
    """Valida no ponto de uso, não na leitura do `.env` inteiro.

    As três senhas não são todas necessárias em toda operação (`alembic
    downgrade` não cria papel nenhum; `make ingest` só conecta como `ingest`,
    nunca como `mcp_reader`) — exigir as três de uma vez em `get_settings()`
    quebrava esses caminhos por uma variável que o comando nem usa.
    """
    if not valor:
        raise RuntimeError(f"variável de ambiente obrigatória ausente: {nome}")
    return valor


def get_settings() -> Settings:
    return Settings(
        postgres_host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_db=os.environ.get("POSTGRES_DB", "pncp_ti"),
        postgres_admin_password=os.environ.get("POSTGRES_ADMIN_PASSWORD"),
        ingest_password=os.environ.get("PNCP_TI_INGEST_PASSWORD"),
        reader_password=os.environ.get("PNCP_TI_READER_PASSWORD"),
        web_password=os.environ.get("PNCP_TI_WEB_PASSWORD"),
        requests_per_second=float(os.environ.get("PNCP_REQUESTS_PER_SECOND", "2")),
        arp_requests_per_second=float(os.environ.get("ARP_REQUESTS_PER_SECOND", "1.5")),
        arp_max_requisicoes=int(os.environ.get("ARP_MAX_REQUISICOES", "20000")),
        arp_varredura_minutos=float(os.environ.get("ARP_VARREDURA_MINUTOS", "45")),
    )


def admin_url(settings: Settings) -> URL:
    """URL estruturada para Alembic, sem interpolação de senha ou ConfigParser."""
    return URL.create(
        "postgresql+psycopg",
        username="postgres",
        password=exigir(settings.postgres_admin_password, "POSTGRES_ADMIN_PASSWORD"),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


def admin_dsn(settings: Settings) -> str:
    """Conninfo libpq: preserva caracteres especiais em senha e nome do banco."""
    return make_conninfo(
        user="postgres",
        password=exigir(settings.postgres_admin_password, "POSTGRES_ADMIN_PASSWORD"),
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
    )


def ingest_dsn(settings: Settings) -> str:
    """Conninfo do papel ingest, usado em runtime."""
    return make_conninfo(
        user="ingest",
        password=exigir(settings.ingest_password, "PNCP_TI_INGEST_PASSWORD"),
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
    )


def reader_dsn(settings: Settings) -> str:
    """Conninfo do papel mcp_reader, usado nas consultas de leitura."""
    return make_conninfo(
        user="mcp_reader",
        password=exigir(settings.reader_password, "PNCP_TI_READER_PASSWORD"),
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
    )


def web_dsn(settings: Settings) -> str:
    """Conninfo do papel web_reader (SELECT só nas views da web, ADR 0018)."""
    return make_conninfo(
        user="web_reader",
        password=exigir(settings.web_password, "PNCP_TI_WEB_PASSWORD"),
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
    )
