"""Migração destrutiva 0004 sobre dados sintéticos do schema anterior.

Histórico: a 0005 a substitui; por isso migra só até a 0004.
"""

import os
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.errors import InsufficientPrivilege

from pncp_ti.config import admin_dsn, get_settings, reader_dsn

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def banco_com_schema_0003():
    settings = get_settings()
    nome = f"pncp_migration_{uuid4().hex}"
    dsn_admin = admin_dsn(replace(settings, postgres_db="postgres"))
    with psycopg.connect(dsn_admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))

    env = os.environ.copy()
    env["POSTGRES_DB"] = nome
    dsn = admin_dsn(replace(settings, postgres_db=nome))
    try:
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "0003"],
            check=True,
            env=env,
            cwd=REPO_ROOT,
        )
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "INSERT INTO orgaos (cnpj, razao_social) VALUES (%s, %s)",
                ("12345678000199", "Órgão sintético"),
            )
            conn.execute(
                "INSERT INTO fornecedores (ni, tipo_pessoa, razao_social_nome, fornecedor_id) "
                "VALUES (%s, 'PJ', %s, %s)",
                ("12345678000199", "Fornecedor sintético", "cnpj:12345678000199"),
            )
            conn.execute(
                "INSERT INTO contratacoes (numero_controle_pncp, cnpj_orgao, raw) "
                "VALUES (%s, %s, '{}'::jsonb)",
                ("compra-sintetica", "12345678000199"),
            )
            conn.execute(
                "INSERT INTO atas (numero_controle_pncp_ata, cnpj_orgao, raw) "
                "VALUES (%s, %s, '{}'::jsonb)",
                ("ata-sintetica", "12345678000199"),
            )
            conn.execute(
                "INSERT INTO contratos (numero_controle_pncp, fornecedor_id, raw) "
                "VALUES (%s, %s, '{}'::jsonb)",
                ("contrato-sintetico", "cnpj:12345678000199"),
            )
            conn.execute(
                "INSERT INTO itens_contratacao (chave, numero_controle_pncp, numero_item, raw) "
                "VALUES (%s, %s, 1, '{}'::jsonb)",
                ("compra-sintetica:1", "compra-sintetica"),
            )
        yield nome, env, dsn
    finally:
        with psycopg.connect(dsn_admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def test_0004_remove_schema_historico_populado_e_cria_view(banco_com_schema_0003):
    nome, env, dsn = banco_com_schema_0003
    subprocess.run(["uv", "run", "alembic", "upgrade", "0004"], check=True, env=env, cwd=REPO_ROOT)

    with psycopg.connect(dsn) as conn:
        tabelas_antigas = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(%s)",
            (["contratacoes", "contratos", "itens_contratacao", "fornecedores"],),
        ).fetchall()
        atas = conn.execute("SELECT count(*) FROM atas").fetchone()[0]
        orgaos = conn.execute("SELECT count(*) FROM orgaos").fetchone()[0]
        view = conn.execute("SELECT to_regclass('public.v_atas_ti_vigentes')").fetchone()[0]
        assert tabelas_antigas == []
        assert atas == orgaos == 0
        assert view == "v_atas_ti_vigentes"

    with psycopg.connect(reader_dsn(replace(get_settings(), postgres_db=nome))) as conn:
        assert conn.execute("SELECT count(*) FROM v_atas_ti_vigentes").fetchone()[0] == 0
        with pytest.raises(InsufficientPrivilege):
            conn.execute("SELECT raw FROM atas LIMIT 1")
