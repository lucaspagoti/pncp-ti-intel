"""Validação do parecer do Codex usada por `review-exec` e `review-qa` (ADR 0029)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/ade-workflow/scripts/validar_parecer.py"
_spec = importlib.util.spec_from_file_location("validar_parecer", SCRIPT)
validar_parecer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validar_parecer)
validar = validar_parecer.validar


def _parecer(**extra):
    base = {
        "snapshot_id": "snap-1",
        "veredito": "APPROVED",
        "arquivos_analisados": ["a.py", "b.py"],
        "verificacoes": ["make test"],
        "limitacoes": [],
        "achados": [],
    }
    return {**base, **extra}


def _qa(**extra):
    evidencia = {"comando": "make test", "resultado": "ok", "arquivo": "qa-out/test.log"}
    return _parecer(**{"deploy_aprovado": True, "evidencias": [evidencia], **extra})


def _p1():
    return {
        "id": "F1",
        "gravidade": "P1",
        "arquivo_linha": "a.py:1",
        "evidencia": "x",
        "impacto": "y",
        "correcao": "z",
    }


def test_parecer_de_revisao_valido():
    assert validar(_parecer(), "snap-1", ["a.py"]) == []


@pytest.mark.parametrize(
    ("parecer", "erro"),
    [
        (_parecer(snapshot_id="outro"), "snapshot_id diverge"),
        (_parecer(veredito="LGTM"), "veredito inválido"),
        (_parecer(arquivos_analisados=["b.py"]), "arquivos esperados não analisados"),
        (_parecer(achados=[_p1()]), "APPROVED com achado P0/P1"),
    ],
)
def test_parecer_de_revisao_invalido(parecer, erro):
    assert any(erro in e for e in validar(parecer, "snap-1", ["a.py"]))


def test_parecer_de_qa_valido():
    assert validar(_qa(), "snap-1", ["a.py"], qa=True) == []


def test_qa_reprovado_sem_deploy_e_valido():
    parecer = _qa(veredito="CHANGES_REQUESTED", deploy_aprovado=False, achados=[_p1()])
    assert validar(parecer, "snap-1", ["a.py"], qa=True) == []


@pytest.mark.parametrize(
    ("parecer", "erro"),
    [
        (_qa(veredito="CHANGES_REQUESTED"), "deploy_aprovado exige APPROVED"),
        (_qa(evidencias=[]), "evidencias vazio"),
        (_qa(deploy_aprovado="sim"), "deploy_aprovado ausente ou não booleano"),
        (_parecer(), "deploy_aprovado ausente ou não booleano"),
    ],
)
def test_parecer_de_qa_invalido(parecer, erro):
    assert any(erro in e for e in validar(parecer, "snap-1", ["a.py"], qa=True))


def test_cli_aceita_e_rejeita(tmp_path):
    caminho = tmp_path / "parecer.json"
    caminho.write_text(json.dumps(_qa()), encoding="utf-8")
    cmd = [sys.executable, "-I", str(SCRIPT), "--qa", str(caminho), "snap-1", "a.py"]
    ok = subprocess.run(cmd, capture_output=True, text=True)
    assert ok.returncode == 0
    assert "ACEITO: APPROVED" in ok.stdout
    assert "deploy_aprovado=true" in ok.stdout

    cmd[-2] = "snap-2"
    rejeitado = subprocess.run(cmd, capture_output=True, text=True)
    assert rejeitado.returncode != 0
    assert "REJEITADO" in rejeitado.stderr
