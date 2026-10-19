"""Gera `prototipos/web/tokens.css` a partir do `tokens.json` do design system.

O design system é material de referência e fica fora do Git (`insumos/design-system/`). Só os
valores entram no repositório, por este gerador; nunca copie um valor à mão.

    uv run python scripts/gerar_tokens_css.py             # regenera
    uv run python scripts/gerar_tokens_css.py --verificar # falha se o CSS versionado divergir
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "insumos" / "design-system" / "tokens.json"
DESTINO = RAIZ / "prototipos" / "web" / "tokens.css"


def gerar(tokens: dict) -> str:
    linhas = [f"  --{t['name']}: {t['value']};" for t in tokens["color"]["tokens"]]
    for nome, familia in tokens["type"]["families"].items():
        linhas.append(f"  --font-{nome}: {familia};")
    for grupo in tokens["type"]["groups"]:
        linhas += [f"  --{s['name']}: {s['fontSize']};" for s in grupo["styles"]]
        linhas += [f"  --{s['name']}-lh: {s['lineHeight']};" for s in grupo["styles"]]
    for secao in ("spacing", "radius", "shadow"):
        linhas += [f"  --{t['name']}: {t['value']};" for t in tokens[secao]["tokens"]]
    return (
        "/* Gerado por scripts/gerar_tokens_css.py a partir de "
        "insumos/design-system/tokens.json. Não edite. */\n"
        ":root {\n" + "\n".join(linhas) + "\n}\n"
        "body { font-family: var(--font-sans); font-variant-numeric: tabular-nums; "
        "color: var(--text); background: var(--bg); }\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verificar", action="store_true", help="só compara, sem escrever")
    parser.add_argument("--origem", type=Path, default=ORIGEM)
    parser.add_argument("--destino", type=Path, default=DESTINO)
    args = parser.parse_args(argv)
    css = gerar(json.loads(args.origem.read_text(encoding="utf-8")))
    if args.verificar:
        atual = args.destino.read_text(encoding="utf-8") if args.destino.exists() else ""
        if atual != css:
            print(f"{args.destino} diverge de {args.origem}; rode o gerador.", file=sys.stderr)
            return 1
        return 0
    args.destino.parent.mkdir(parents=True, exist_ok=True)
    args.destino.write_text(css, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
