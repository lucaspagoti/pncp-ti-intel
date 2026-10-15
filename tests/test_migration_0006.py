"""Migração 0006: `vigente_na_origem`, colunas da ARP, views novas e fim do log legado."""

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
def banco_na_0005():
    settings = get_settings()
    nome = f"pncp_mig6_{uuid4().hex}"
    dsn_admin = admin_dsn(replace(settings, postgres_db="postgres"))
    with psycopg.connect(dsn_admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    env = {**os.environ, "POSTGRES_DB": nome}
    try:
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "0005"], check=True, env=env, cwd=REPO_ROOT
        )
        yield env, admin_dsn(replace(settings, postgres_db=nome))
    finally:
        with psycopg.connect(dsn_admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def test_0006_preenche_vigente_na_origem_do_siga_e_remove_o_log_legado(banco_na_0005):
    env, dsn = banco_na_0005
    carga = uuid4()
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
            "VALUES (%s, 'siga_rj', '2026-10-13', 'concluida', true)",
            (carga,),
        )
        for id_origem, status in (("1", "Válida"), ("2", "Interrompida")):
            conn.execute(
                "INSERT INTO atas (carga_id, id_origem, numero, objeto, status_origem, "
                "is_ti, fim) VALUES (%s, %s, %s, 'notebooks', %s, true, '2099-12-31')",
                (carga, id_origem, id_origem, status),
            )
        assert conn.execute("SELECT to_regclass('public.log_execucao_ingestao')").fetchone()[0]

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env, cwd=REPO_ROOT)

    with psycopg.connect(dsn) as conn:
        vigentes = dict(conn.execute("SELECT id_origem, vigente_na_origem FROM atas").fetchall())
        assert vigentes == {"1": True, "2": False}
        assert (
            conn.execute("SELECT to_regclass('public.log_execucao_ingestao')").fetchone()[0] is None
        )
        ata_ids = [r[0] for r in conn.execute("SELECT id_ata FROM v_atas_ti_vigentes").fetchall()]
        assert ata_ids == ["1"]
        colunas = {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'v_ata_itens_ti'"
            ).fetchall()
        }
        assert {"codigo_pdm", "maximo_adesao", "quantidade_empenhada", "tipo_item"} <= colunas


def test_0006_nao_tem_downgrade(banco_na_0005):
    env, _ = banco_na_0005
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env, cwd=REPO_ROOT)
    resultado = subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0005"],
        env=env, cwd=REPO_ROOT, capture_output=True, text=True,
    )  # fmt: skip
    assert resultado.returncode != 0
    assert "não tem downgrade" in resultado.stderr
