"""Migração 0005: substitui o schema do snapshot `/v1/atas` (0004) pelo modelo multi-fonte."""

import os
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from pncp_ti.config import admin_dsn, get_settings

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def banco_na_0004():
    settings = get_settings()
    nome = f"pncp_mig5_{uuid4().hex}"
    dsn_admin = admin_dsn(replace(settings, postgres_db="postgres"))
    with psycopg.connect(dsn_admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    env = {**os.environ, "POSTGRES_DB": nome}
    try:
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "0004"], check=True, env=env, cwd=REPO_ROOT
        )
        yield nome, env, admin_dsn(replace(settings, postgres_db=nome))
    finally:
        with psycopg.connect(dsn_admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def test_0005_troca_o_schema_e_remove_o_snapshot_antigo(banco_na_0004):
    _, env, dsn = banco_na_0004
    snapshot = uuid4()
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO snapshots_atas_ti (id, data_referencia, status, ativo) "
            "VALUES (%s, '2026-10-12', 'concluido', true)",
            (snapshot,),
        )
        conn.execute(
            "INSERT INTO atas (numero_controle_pncp_ata, snapshot_id, chave_snapshot, raw) "
            "VALUES ('ata-antiga', %s, 'k', '{}'::jsonb)",
            (snapshot,),
        )

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env, cwd=REPO_ROOT)

    with psycopg.connect(dsn) as conn:
        existentes = {
            r[0]
            for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        }
        assert {"cargas", "atas", "ata_itens", "ata_participantes", "atas_vistas"} <= existentes
        assert not {"snapshots_atas_ti", "amostra_atas_descartadas", "orgaos"} & existentes
        colunas = {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'atas'"
            ).fetchall()
        }
        assert {"carga_id", "id_origem", "is_ti", "motivo_ti", "processos"} <= colunas
        assert "raw" not in colunas
        assert conn.execute("SELECT count(*) FROM atas").fetchone()[0] == 0
        views = {
            r[0] for r in conn.execute("SELECT viewname FROM pg_views WHERE schemaname='public'")
        }
        assert {"v_atas_ti_vigentes", "v_ata_itens_ti", "v_ata_consumo_item"} <= views


def test_0005_nao_tem_downgrade(banco_na_0004):
    _, env, _ = banco_na_0004
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env, cwd=REPO_ROOT)
    resultado = subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0004"],
        env=env, cwd=REPO_ROOT, capture_output=True, text=True,
    )  # fmt: skip
    assert resultado.returncode != 0
    assert "não tem downgrade" in resultado.stderr
