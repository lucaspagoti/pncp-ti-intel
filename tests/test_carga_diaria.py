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
    for fonte in ("siga", "arp", "pncp_atas", "pncp_busca"):
        if fonte not in saidas:
            (tmp_path / f"saidas_{fonte}").write_text("")
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
    codigo, chamadas, _ = rodar(tmp_path, {"siga": [0], "arp": [0], "pncp_atas": [0]})
    assert (codigo, chamadas) == (0, ["siga", "arp", "pncp_atas"])


def test_api_oficial_falha_e_a_busca_do_portal_entra_na_hora(tmp_path):
    for saida_api in (1, 2):
        (tmp_path / "chamadas").unlink(missing_ok=True)
        dir_ = tmp_path / f"t{saida_api}"
        dir_.mkdir()
        codigo, chamadas, erro = rodar(
            dir_, {"siga": [0], "arp": [0], "pncp_atas": [saida_api], "pncp_busca": [0]}
        )
        assert (codigo, chamadas) == (0, ["siga", "arp", "pncp_atas", "pncp_busca"])
        assert "usando a busca do portal" in erro


def test_busca_instavel_ganha_nova_tentativa_e_recupera(tmp_path):
    codigo, chamadas, _ = rodar(
        tmp_path, {"siga": [0], "arp": [0], "pncp_atas": [1], "pncp_busca": [1, 0]}
    )
    assert (codigo, chamadas) == (0, ["siga", "arp", "pncp_atas", "pncp_busca", "pncp_busca"])


def test_falha_de_novo_na_nova_tentativa_falha_a_carga(tmp_path):
    codigo, chamadas, erro = rodar(
        tmp_path, {"siga": [0], "arp": [0], "pncp_atas": [1], "pncp_busca": [1, 1]}
    )
    assert (codigo, chamadas) == (1, ["siga", "arp", "pncp_atas", "pncp_busca", "pncp_busca"])
    assert "depois da nova tentativa" in erro


@pytest.mark.parametrize("fonte,codigo_saida", [("arp", 1), ("siga", 2)])
def test_arp_e_erro_deterministico_nao_repetem(tmp_path, fonte, codigo_saida):
    saidas = {"siga": [0], "arp": [0], "pncp_atas": [0], fonte: [codigo_saida]}
    codigo, chamadas, _ = rodar(tmp_path, saidas)
    assert (codigo, chamadas) == (1, ["siga", "arp", "pncp_atas"])


def test_reserva_com_erro_deterministico_falha_sem_repetir(tmp_path):
    saidas = {"siga": [0], "arp": [0], "pncp_atas": [2], "pncp_busca": [2]}
    codigo, chamadas, _ = rodar(tmp_path, saidas)
    assert (codigo, chamadas) == (1, ["siga", "arp", "pncp_atas", "pncp_busca"])


def test_sem_folga_ate_o_limite_nao_repete(tmp_path):
    codigo, chamadas, erro = rodar(
        tmp_path,
        {"siga": [0], "arp": [0], "pncp_atas": [1], "pncp_busca": [1, 0]},
        PNCP_TI_ESPERA_NOVA_TENTATIVA="10",
        PNCP_TI_LIMITE_NOVA_TENTATIVA="5",
    )
    assert (codigo, chamadas) == (1, ["siga", "arp", "pncp_atas", "pncp_busca"])
    assert "sem tempo para nova tentativa" in erro
