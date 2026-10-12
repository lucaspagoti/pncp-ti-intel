"""Mascaramento de CPF — regra fixa do CLAUDE.md: nenhum CPF completo nesta base."""

from __future__ import annotations


def mascarar_ni(ni: str | None, tipo_pessoa: str | None) -> str | None:
    """Mascara CPF (pessoa física); CNPJ passa direto (não é dado pessoal)."""
    if not ni:
        return None
    digitos = "".join(c for c in ni if c.isdigit())
    if tipo_pessoa != "PF" and len(digitos) != 11:
        return digitos
    if len(digitos) <= 5:
        return "*" * len(digitos)
    return f"{digitos[:3]}{'*' * (len(digitos) - 5)}{digitos[-2:]}"
