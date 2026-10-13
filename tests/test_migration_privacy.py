"""Upgrade de banco legado sem inferir identidade a partir de máscara colidente."""

import importlib.util
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

from pncp_ti.config import admin_dsn, get_settings

ROOT = Path(__file__).resolve().parents[1]


def test_migracao_limpa_raw_legado_e_desvincula_pf_ambiguo():
    settings = get_settings()
    name = f"pncp_migration_{uuid4().hex}"
    env = os.environ | {"POSTGRES_DB": name}
    maintenance = admin_dsn(replace(settings, postgres_db="postgres"))
    with psycopg.connect(maintenance, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            subprocess.run(
                ["uv", "run", "alembic", "upgrade", "0001"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
            )
            with psycopg.connect(admin_dsn(replace(settings, postgres_db=name))) as seed:
                seed.execute(
                    "INSERT INTO fornecedores (ni,tipo_pessoa) VALUES "
                    "('123******90','PF'), ('12345678000190','PJ')"
                )
                seed.execute(
                    "INSERT INTO contratos (numero_controle_pncp,ni_fornecedor,raw) "
                    "VALUES ('pf','123******90',%s::jsonb), "
                    "('pj','12345678000190','{}')",
                    ('{"niFornecedorSubContratado":"12300002590","tipoPessoaSubContratada":"PF"}',),
                )
            subprocess.run(
                ["uv", "run", "alembic", "upgrade", "0002"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
            )
            with psycopg.connect(admin_dsn(replace(settings, postgres_db=name))) as check:
                pf = check.execute(
                    "SELECT fornecedor_id,raw FROM contratos WHERE numero_controle_pncp='pf'"
                ).fetchone()
                assert pf[0] is None
                assert pf[1]["niFornecedorSubContratado"] == "123******90"
                assert check.execute(
                    "SELECT fornecedor_id FROM contratos WHERE numero_controle_pncp='pj'"
                ).fetchone()[0] == ("cnpj:12345678000190")
        finally:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_redacao_legada_cobre_cpf_curto_sem_alterar_preco():
    path = ROOT / "db/migrations/versions/0002_supplier_identity.py"
    spec = importlib.util.spec_from_file_location("supplier_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = {"cpfResponsavel": 1234567890, "cpfNovo": "1234567890", "valorGlobal": 12345678901}
    result = module._redact(value)
    assert result["cpfResponsavel"] == "123*****90"
    assert result["cpfNovo"] == "123*****90"
    assert result["valorGlobal"] == value["valorGlobal"]
