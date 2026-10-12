"""Configuração da camada de ingestão, carregada do `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


def _find_dotenv() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return Path(".env")


load_dotenv(_find_dotenv())


@dataclass(frozen=True, slots=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_admin_password: str
    ingest_password: str
    reader_password: str
    requests_per_second: float
    backfill_start: date


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"variável de ambiente obrigatória ausente: {name}")
    return value


def get_settings() -> Settings:
    return Settings(
        postgres_host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_db=os.environ.get("POSTGRES_DB", "pncp_ti"),
        postgres_admin_password=_require("POSTGRES_ADMIN_PASSWORD"),
        ingest_password=_require("PNCP_TI_INGEST_PASSWORD"),
        reader_password=_require("PNCP_TI_READER_PASSWORD"),
        requests_per_second=float(os.environ.get("PNCP_REQUESTS_PER_SECOND", "2")),
        backfill_start=date.fromisoformat(os.environ.get("INGEST_BACKFILL_START", "2023-04-01")),
    )


def admin_dsn(settings: Settings) -> str:
    """DSN com o usuário administrador do Postgres — só para migrações (Alembic)."""
    return (
        f"postgresql://postgres:{settings.postgres_admin_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def ingest_dsn(settings: Settings) -> str:
    """DSN com o papel `ingest` (só INSERT/UPDATE/SELECT nas tabelas base) — usado em runtime."""
    return (
        f"postgresql://ingest:{settings.ingest_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
