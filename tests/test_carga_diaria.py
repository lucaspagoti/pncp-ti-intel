"""`scripts/carga_diaria.sh`: nova tentativa da fonte instável (ADR 0037), sem rede nem banco."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def rodar(tmp_path: Path, saidas: dict[str, list[int]], **env: str) -> tuple[int, list[str], str]:
    """Copia o script para uma árvore falsa com um `uv` que devolve as saídas por fonte."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(RAIZ / "scripts" / "carga_diaria.sh", tmp_path / "scripts")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for fonte, codigos in saidas.items():
        (tmp_path / f"saidas_{fonte}").write_text("\n".join(map(str, codigos)) + "\n")
    uv = bin_ / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'fonte="${4##*.}"\n'
        'echo "$fonte" >> chamadas\n'
        'arq="saidas_$fonte"\n'
        'codigo=$(head -1 "$arq"); sed -i 1d "$arq"\n'
        'exit "${codigo:-0}"\n'
    )
    uv.chmod(0o755)
    ambiente = {
        **os.environ,
        "PATH": f"{bin_}:{os.environ['PATH']}",
        "PNCP_TI_ESPERA_NOVA_TENTATIVA": "0",
        **env,
    }
    r = subprocess.run(
        ["bash", str(tmp_path / "scripts" / "carga_diaria.sh")],
        cwd=tmp_path,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=30,
    )
    chamadas = (tmp_path / "chamadas").read_text().split()
    return r.returncode, chamadas, r.stderr


@pytest.fixture(autouse=True)
def precisa_bash():
    if shutil.which("bash") is None:
        pytest.skip("sem bash")


def test_tudo_certo_nao_repete(tmp_path):
    codigo, chamadas, _ = rodar(tmp_path, {"siga": [0], "arp": [0], "pncp_busca": [0]})
    assert (codigo, chamadas) == (0, ["siga", "arp", "pncp_busca"])


def test_busca_instavel_ganha_nova_tentativa_e_recupera(tmp_path):
    codigo, chamadas, _ = rodar(tmp_path, {"siga": [0], "arp": [0], "pncp_busca": [1, 0]})
    assert (codigo, chamadas) == (0, ["siga", "arp", "pncp_busca", "pncp_busca"])


def test_falha_de_novo_na_nova_tentativa_falha_a_carga(tmp_path):
    codigo, chamadas, erro = rodar(tmp_path, {"siga": [0], "arp": [0], "pncp_busca": [1, 1]})
    assert (codigo, chamadas) == (1, ["siga", "arp", "pncp_busca", "pncp_busca"])
    assert "depois da nova tentativa" in erro


@pytest.mark.parametrize("fonte,codigo_saida", [("arp", 1), ("pncp_busca", 2), ("siga", 2)])
def test_arp_e_erro_deterministico_nao_repetem(tmp_path, fonte, codigo_saida):
    saidas = {"siga": [0], "arp": [0], "pncp_busca": [0], fonte: [codigo_saida]}
    codigo, chamadas, _ = rodar(tmp_path, saidas)
    assert (codigo, chamadas) == (1, ["siga", "arp", "pncp_busca"])


def test_sem_folga_ate_o_limite_nao_repete(tmp_path):
    codigo, chamadas, erro = rodar(
        tmp_path,
        {"siga": [0], "arp": [0], "pncp_busca": [1, 0]},
        PNCP_TI_ESPERA_NOVA_TENTATIVA="10",
        PNCP_TI_LIMITE_NOVA_TENTATIVA="5",
    )
    assert (codigo, chamadas) == (1, ["siga", "arp", "pncp_busca"])
    assert "sem tempo para nova tentativa" in erro
