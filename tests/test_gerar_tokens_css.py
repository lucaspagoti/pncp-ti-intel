"""Gerador do tokens.css: o CSS sai do tokens.json, nunca de valores copiados à mão."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("gerar", RAIZ / "scripts" / "gerar_tokens_css.py")
gerar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gerar)

TOKENS = {
    "color": {"tokens": [{"name": "navy", "value": "#005a92", "usage": "x"}]},
    "type": {
        "families": {"sans": "Calibri, Arial, sans-serif"},
        "groups": [{"styles": [{"name": "fs-xs", "fontSize": "0.78rem", "lineHeight": 1.45}]}],
    },
    "spacing": {"tokens": [{"name": "space-1", "value": "4px"}]},
    "radius": {"tokens": [{"name": "radius-sm", "value": "4px"}]},
    "shadow": {"tokens": [{"name": "shadow-pop", "value": "0 6px 20px rgba(0,0,0,.16)"}]},
}


def test_gera_variaveis_de_todas_as_secoes():
    css = gerar.gerar(TOKENS)
    for linha in (
        "--navy: #005a92;",
        "--font-sans: Calibri, Arial, sans-serif;",
        "--fs-xs: 0.78rem;",
        "--fs-xs-lh: 1.45;",
        "--space-1: 4px;",
        "--radius-sm: 4px;",
        "--shadow-pop: 0 6px 20px rgba(0,0,0,.16);",
    ):
        assert linha in css
    assert "tabular-nums" in css


def test_verificar_acusa_css_divergente(tmp_path):
    origem = tmp_path / "tokens.json"
    destino = tmp_path / "tokens.css"
    origem.write_text(json.dumps(TOKENS), encoding="utf-8")
    assert gerar.main(["--origem", str(origem), "--destino", str(destino), "--verificar"]) == 1
    assert gerar.main(["--origem", str(origem), "--destino", str(destino)]) == 0
    assert gerar.main(["--origem", str(origem), "--destino", str(destino), "--verificar"]) == 0
    destino.write_text(destino.read_text() + "/* à mão */", encoding="utf-8")
    assert gerar.main(["--origem", str(origem), "--destino", str(destino), "--verificar"]) == 1
