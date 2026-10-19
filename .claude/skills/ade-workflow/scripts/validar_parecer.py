"""Valida o parecer JSON do Codex (`review-exec` e, com `--qa`, `review-qa`; ADR 0029).

Uso: validar_parecer.py [--qa] PARECER SNAPSHOT_ID ARQUIVO_ESPERADO...
Sai com 0 e imprime ACEITO, ou sai com erro e imprime REJEITADO no stderr.
Só biblioteca padrão: roda com `python3 -I`, fora do ambiente do projeto.
"""

from __future__ import annotations

import json
import sys


def validar(p: dict, snapshot: str, esperados: list[str], *, qa: bool = False) -> list[str]:
    erros = []
    if p.get("snapshot_id") != snapshot:
        erros.append("snapshot_id diverge")
    if p.get("veredito") not in ("APPROVED", "CHANGES_REQUESTED"):
        erros.append("veredito inválido")
    faltam = [f for f in esperados if f not in p.get("arquivos_analisados", [])]
    if faltam:
        erros.append(f"arquivos esperados não analisados: {faltam}")
    graves = [a for a in p.get("achados", []) if a.get("gravidade") in ("P0", "P1")]
    if p.get("veredito") == "APPROVED" and graves:
        erros.append("APPROVED com achado P0/P1")
    if qa:
        deploy = p.get("deploy_aprovado")
        if not isinstance(deploy, bool):
            erros.append("deploy_aprovado ausente ou não booleano")
        elif deploy and p.get("veredito") != "APPROVED":
            erros.append("deploy_aprovado exige APPROVED")
        if not p.get("evidencias"):
            erros.append("evidencias vazio")
    return erros


def main(argv: list[str]) -> int:
    qa = "--qa" in argv
    args = [a for a in argv if a != "--qa"]
    if len(args) < 2:
        print("uso: validar_parecer.py [--qa] PARECER SNAPSHOT_ID ARQUIVO...", file=sys.stderr)
        return 64
    caminho, snapshot, *esperados = args
    with open(caminho, encoding="utf-8") as f:
        p = json.load(f)
    erros = validar(p, snapshot, esperados, qa=qa)
    if erros:
        print("REJEITADO: " + "; ".join(erros), file=sys.stderr)
        return 1
    resumo = f"ACEITO: {p['veredito']} ({len(p['achados'])} achados) snapshot={snapshot}"
    if qa:
        resumo += f" deploy_aprovado={'true' if p['deploy_aprovado'] else 'false'}"
    print(resumo)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
