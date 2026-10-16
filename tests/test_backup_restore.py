"""Scripts operacionais: publicação atômica e destinos protegidos, sem banco real."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def backup_repo(tmp_path, fail_dump=False, fail_validation=False, fail_restore=False):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "bin").mkdir()
    shutil.copy(ROOT / "scripts/backup_postgres.sh", tmp_path / "scripts")
    shutil.copy(ROOT / "scripts/verificar_backup.sh", tmp_path / "scripts")
    # Executar este arquivo como shell seria uma vulnerabilidade.
    (tmp_path / ".env").write_text("PASSWORD=$(touch EXECUTED)\n")
    fake = tmp_path / "bin/docker"
    fake.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> calls.log\n'
        'case "$*" in\n'
        '*pg_dump*) printf "dump bytes"; exit "$FAIL_DUMP";;\n'
        '*pg_restore*--list*) cat >/dev/null; exit "$FAIL_VALIDATION";;\n'
        '*pg_restore*) cat >/dev/null; exit "$FAIL_RESTORE";;\n'
        "*createdb*|*dropdb*|*psql*) cat >/dev/null; exit 0;;\n"
        "*) exit 9;;\nesac\n"
    )
    fake.chmod(0o755)
    env = os.environ | {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "FAIL_DUMP": str(int(fail_dump)),
        "FAIL_VALIDATION": str(int(fail_validation)),
        "FAIL_RESTORE": str(int(fail_restore)),
    }
    result = subprocess.run(
        ["bash", str(tmp_path / "scripts/backup_postgres.sh")], env=env, capture_output=True
    )
    return result


def test_backup_published_private_without_executing_env(tmp_path):
    result = backup_repo(tmp_path)
    assert result.returncode == 0
    dumps = list((tmp_path / "backups").glob("*.dump"))
    assert len(dumps) == 1
    assert dumps[0].read_bytes() == b"dump bytes"
    assert dumps[0].stat().st_mode & 0o777 == 0o600
    assert not list((tmp_path / "backups").glob("*.partial"))
    assert not (tmp_path / "EXECUTED").exists()


@pytest.mark.parametrize("dump_failure", [True, False])
def test_backup_failure_removes_partial(tmp_path, dump_failure):
    result = backup_repo(tmp_path, fail_dump=dump_failure, fail_validation=not dump_failure)
    assert result.returncode != 0
    assert not list((tmp_path / "backups").iterdir())


def test_backup_restoration_failure_cleans_only_created_database_and_never_publishes(tmp_path):
    result = backup_repo(tmp_path, fail_restore=True)
    assert result.returncode != 0
    assert not list((tmp_path / "backups").iterdir())
    chamadas = (tmp_path / "calls.log").read_text().splitlines()
    criado = next(c for c in chamadas if "createdb" in c).split()[-1]
    removido = next(c for c in chamadas if "dropdb" in c).split()[-1]
    assert criado.startswith("pncp_backup_check_")
    assert criado == removido
    assert not any("psql" in c for c in chamadas)


@pytest.mark.parametrize("database", ["pncp_ti", "postgres", "template0", "bad;SQL", "x" * 64])
def test_restore_rejects_protected_or_invalid_destination(database):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/restore_postgres.sh"), "missing.dump", "--database", database],
        env=os.environ | {"POSTGRES_DB": "pncp_ti"},
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert "nome do banco" in result.stderr or "banco atual" in result.stderr
