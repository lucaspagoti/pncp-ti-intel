"""Migração 0011: busca por item populada na subida, papéis certos e a 0010 de volta na descida."""

import os
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from pncp_ti.config import admin_dsn, get_settings, web_dsn

REPO_ROOT = Path(__file__).parent.parent


def _alembic(env, *args):
    subprocess.run(["uv", "run", "alembic", *args], check=True, env=env, cwd=REPO_ROOT)


@pytest.fixture
def banco_na_0010():
    settings = get_settings()
    nome = f"pncp_mig11_{uuid4().hex}"
    dsn_admin = admin_dsn(replace(settings, postgres_db="postgres"))
    with psycopg.connect(dsn_admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    env = {**os.environ, "POSTGRES_DB": nome}
    try:
        _alembic(env, "upgrade", "0010")
        yield env, nome
    finally:
        with psycopg.connect(dsn_admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def test_0011_popula_itens_e_volta_para_a_0010(banco_na_0010):
    env, nome = banco_na_0010
    configuracao = replace(get_settings(), postgres_db=nome)
    carga = uuid4()
    with psycopg.connect(admin_dsn(configuracao)) as conn:
        conn.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
            "VALUES (%s, 'compras_arp', current_date, 'concluida', true)",
            (carga,),
        )
        conn.execute(
            "INSERT INTO atas (carga_id, id_origem, numero, objeto, status_origem, is_ti, "
            "vigente_na_origem, fim) "
            "VALUES (%s, 'A1', '1', 'Informática', 'Ativa', true, true, %s)",
            (carga, date.today() + timedelta(days=30)),
        )
        conn.execute(
            "INSERT INTO ata_itens (carga_id, chave, ata_id_origem, id_item, descricao, "
            "nome_catalogo, valor_unitario, valor_valido) VALUES "
            "(%s, 'k1', 'A1', '1', 'MONITOR COMPUTADOR, 24 POL', 'MONITOR COMPUTADOR', 700, true), "
            "(%s, 'k2', 'A1', '2', 'Cabo HDMI - 2 metros', '', 30, true)",
            (carga, carga),
        )
    _alembic(env, "upgrade", "0011")
    with psycopg.connect(admin_dsn(configuracao)) as conn:
        itens = conn.execute(
            "SELECT cabeca, cabeca_texto FROM v_busca_itens ORDER BY id_item"
        ).fetchall()
        assert itens == [("monitor computador", "MONITOR COMPUTADOR"), ("cabo hdmi", "Cabo HDMI")]
        assert conn.execute(
            "SELECT count(*) FROM v_busca_atas "
            "WHERE objeto_exato @@ to_tsquery('simple', 'informatica')"
        ).fetchone() == (1,)
        assert ("monitor",) in conn.execute("SELECT palavra FROM v_busca_vocabulario").fetchall()
        conn.execute("SELECT atualizar_busca()")  # refresh das três MVs
    with psycopg.connect(web_dsn(configuracao), autocommit=True) as leitor:
        leitor.execute("SELECT count(*) FROM v_busca_itens")
        leitor.execute("SELECT count(*) FROM v_busca_vocabulario")
        for mv in ("mv_busca_itens", "mv_busca_vocabulario"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                leitor.execute(f"SELECT * FROM {mv}")
    _alembic(env, "downgrade", "0010")
    with psycopg.connect(admin_dsn(configuracao)) as conn:
        assert conn.execute("SELECT id_ata FROM v_busca_atas").fetchall() == [("A1",)]
        assert conn.execute("SELECT to_regclass('mv_busca_itens')").fetchone() == (None,)
        conn.execute("SELECT atualizar_busca()")
