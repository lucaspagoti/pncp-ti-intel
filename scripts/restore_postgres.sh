#!/usr/bin/env bash
# Restaura apenas para um banco novo, explicitamente nomeado.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python - "$@" <<'PY'
from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

from pncp_ti.config import admin_dsn, get_settings

parser = argparse.ArgumentParser(description="Restaura dump em banco NOVO; preserva o banco atual.")
parser.add_argument("dump", type=Path)
parser.add_argument("--database", required=True, help="Nome explícito do novo banco de destino")
args = parser.parse_args()
settings = get_settings()
if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", args.database):
    parser.error("nome do banco deve ter 1–63 caracteres: letras minúsculas, números e underscore")
if args.database in {settings.postgres_db, "postgres", "template0", "template1"}:
    parser.error("o destino não pode ser o banco atual nem um banco de sistema")
if not args.dump.is_file():
    parser.error("arquivo de dump inexistente")
compose = ["docker", "compose", "--env-file", ".env", "exec", "-T", "postgres"]
with args.dump.open("rb") as source:
    subprocess.run(compose + ["pg_restore", "--list"], stdin=source, stdout=subprocess.DEVNULL,
                   check=True)
maintenance = admin_dsn(replace(settings, postgres_db="postgres"))
with psycopg.connect(maintenance, autocommit=True) as conn:
    if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.database,)).fetchone():
        parser.error("o banco de destino já existe; nenhum dado foi alterado")
    # pg_dump não inclui papéis globais. Migra em banco descartável separado para
    # provisionar papéis ausentes; nunca aplica schema sobre o destino do restore.
    provision = f"pncp_restore_roles_{uuid4().hex}"
    conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(provision)))
    try:
        env = os.environ.copy()
        env["POSTGRES_DB"] = provision
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], env=env, check=True)
    finally:
        conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(provision)))
    conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(args.database)))
with args.dump.open("rb") as source:
    try:
        subprocess.run(compose + ["pg_restore", "-U", "postgres", "--exit-on-error",
                                  "--single-transaction", "-d", args.database],
                       stdin=source, check=True)
    except subprocess.CalledProcessError:
        raise SystemExit("Restauração falhou; destino novo preservado para diagnóstico, "
                         "banco atual intacto.") from None
print(f"Backup restaurado em {args.database}. Banco atual preservado.")
PY
