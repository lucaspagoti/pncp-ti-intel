"""Scripts da esteira de QA (ADR 0029) com Docker, Codex e uv simulados: sem serviços reais."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent.parent
PG = RAIZ / "scripts/pg_descartavel.sh"
REVIEW_QA = RAIZ / ".claude/skills/ade-workflow/scripts/review-qa"

DOCKER_FALSO = """#!/usr/bin/env bash
echo "$*" >> "$REGISTRO"
case $1 in
  run) [[ -n ${DOCKER_RUN_FALHA:-} ]] && exit 125; echo id ;;
  exec) exit 0 ;;
  port) [[ -n ${DOCKER_PORT_FALHA:-} ]] && exit 42; echo 127.0.0.1:55432 ;;
  inspect) exit 1 ;;
  rm) exit 0 ;;
esac
"""


def _bin_falso(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for nome, corpo in {
        "docker": DOCKER_FALSO,
        "codex": "#!/bin/sh\nexit 1\n",
        "uv": "#!/bin/sh\nexit 1\n",
    }.items():
        exe = bin_dir / nome
        exe.write_text(corpo)
        exe.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REGISTRO": str(tmp_path / "docker.log"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }


def _chamadas_docker(tmp_path: Path) -> list[str]:
    registro = tmp_path / "docker.log"
    return registro.read_text().splitlines() if registro.exists() else []


def test_pg_descartavel_grava_env_0600_mesmo_com_destino_existente(tmp_path):
    env = _bin_falso(tmp_path)
    destino = tmp_path / "qa.env"
    destino.write_text("antigo\n")
    destino.chmod(0o644)
    r = subprocess.run([PG, "up", "teste", destino], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert stat.S_IMODE(destino.stat().st_mode) == 0o600
    conteudo = destino.read_text()
    assert "POSTGRES_PORT=55432" in conteudo and "antigo" not in conteudo


def test_pg_descartavel_remove_o_conteiner_que_criou_se_falhar_depois(tmp_path):
    env = {**_bin_falso(tmp_path), "DOCKER_PORT_FALHA": "1"}
    destino = tmp_path / "qa.env"
    r = subprocess.run([PG, "up", "teste", destino], env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert "rm -f -v pncp-ti-qa-teste" in _chamadas_docker(tmp_path)
    assert not destino.exists()
    assert not list(tmp_path.glob(".pg_descartavel.*"))


def test_review_qa_nao_apaga_clone_de_outra_execucao(tmp_path):
    env = _bin_falso(tmp_path)
    alheio = tmp_path / "cache/pncp-ti/qa/snap-x"
    alheio.mkdir(parents=True)
    (alheio / "evidencia").write_text("de outra execução")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("x")
    r = subprocess.run(
        [REVIEW_QA, "snap-x", "HEAD", prompt, tmp_path / "out", "Makefile"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert (alheio / "evidencia").exists()
    assert not any(c.startswith("rm") for c in _chamadas_docker(tmp_path))


def test_review_qa_nao_remove_conteiner_que_nao_criou(tmp_path):
    env = {**_bin_falso(tmp_path), "DOCKER_RUN_FALHA": "1"}
    prompt = tmp_path / "prompt.md"
    prompt.write_text("x")
    r = subprocess.run(
        [REVIEW_QA, "snap-y", "HEAD", prompt, tmp_path / "out", "Makefile"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    chamadas = _chamadas_docker(tmp_path)
    assert any(c.startswith("run") for c in chamadas)
    assert not any(c.startswith("rm") for c in chamadas)
    assert not (tmp_path / "cache/pncp-ti/qa/snap-y").exists()
