"""Migração 0010: busca materializada populada na subida e view da 0008 de volta na descida."""

import os
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from pncp_ti.config import admin_dsn, get_settings

REPO_ROOT = Path(__file__).parent.parent


def _alembic(env, *args):
    subprocess.run(["uv", "run", "alembic", *args], check=True, env=env, cwd=REPO_ROOT)


@pytest.fixture
def banco_na_0009():
    settings = get_settings()
    nome = f"pncp_mig10_{uuid4().hex}"
    dsn_admin = admin_dsn(replace(settings, postgres_db="postgres"))
    with psycopg.connect(dsn_admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    env = {**os.environ, "POSTGRES_DB": nome}
    try:
        _alembic(env, "upgrade", "0009")
        yield env, admin_dsn(replace(settings, postgres_db=nome))
    finally:
        with psycopg.connect(dsn_admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def test_0010_materializa_a_busca_existente_e_volta(banco_na_0009):
    env, dsn = banco_na_0009
    carga = uuid4()
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
            "VALUES (%s, 'compras_arp', current_date, 'concluida', true)",
            (carga,),
        )
        conn.execute(
            "INSERT INTO atas (carga_id, id_origem, numero, objeto, status_origem, is_ti, "
            "vigente_na_origem, fim) VALUES (%s, 'A1', '1', 'Notebooks', 'Ativa', true, true, %s)",
            (carga, date.today() + timedelta(days=30)),
        )
    _alembic(env, "upgrade", "0010")
    with psycopg.connect(dsn) as conn:
        consulta = (
            "SELECT id_ata FROM v_busca_atas WHERE documento @@ "
            "websearch_to_tsquery('portuguese', 'notebooks')"
        )
        assert conn.execute(consulta).fetchall() == [("A1",)]
        assert conn.execute("SELECT fonte FROM v_cargas_web").fetchall() == [("compras_arp",)]
    _alembic(env, "downgrade", "0009")
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT id_ata FROM v_busca_atas").fetchall() == [("A1",)]
        assert conn.execute("SELECT to_regclass('mv_busca_atas')").fetchone() == (None,)
        assert conn.execute("SELECT to_regclass('unidades_gerenciadoras')").fetchone() == (None,)
