"""Sanitização de dados e identidade pseudonimizada de fornecedores (ADR 0013)."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from typing import Any

from pncp_ti.config import exigir
from pncp_ti.mask import mascarar_ni

CPF_PATTERN = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")


def sanitizar(valor: Any) -> Any:
    """Copia JSON e mascara CPFs inclusive em campos novos/texto livre.

    Sequências isoladas de 11 dígitos são tratadas conservadoramente como CPF.
    CNPJ de 14 dígitos não casa; tipos e dados não pessoais são preservados.
    """
    if isinstance(valor, dict):
        copia = {
            k: mascarar_ni(v, "PF")
            if "cpf" in k.lower() and v is not None and isinstance(v, (str, int))
            else sanitizar(v)
            for k, v in valor.items()
        }
        for campo, tipo in (
            ("niFornecedor", "tipoPessoa"),
            ("niFornecedorSubContratado", "tipoPessoaSubContratada"),
        ):
            if campo in valor:
                copia[campo] = mascarar_ni(valor[campo], valor.get(tipo))
        return copia
    if isinstance(valor, list):
        return [sanitizar(v) for v in valor]
    if isinstance(valor, str):
        return CPF_PATTERN.sub(lambda m: mascarar_ni(m.group(), "PF") or "", valor)
    return valor


def identificar_fornecedor(payload: dict[str, Any]) -> str | None:
    """CPF completo só existe em memória; HMAC não permite ataques por enumeração sem chave.

    Identificador já mascarado na origem não identifica uma pessoa: escopo por
    contrato impede fundir pessoas distintas com a mesma máscara upstream.
    """
    ni = payload.get("niFornecedor")
    if ni in (None, ""):
        return None
    documento = str(ni).strip()
    digitos = "".join(c for c in documento if c.isdigit())
    if payload.get("tipoPessoa") == "PJ" and len(digitos) == 14 and "*" not in documento:
        return f"cnpj:{digitos}"
    chave = exigir(os.environ.get("PNCP_TI_IDENTITY_KEY"), "PNCP_TI_IDENTITY_KEY")
    if len(chave.encode()) < 32:
        raise RuntimeError("PNCP_TI_IDENTITY_KEY deve ter pelo menos 32 bytes")
    if "*" in documento or len(digitos) != 11:
        contexto = payload["numeroControlePNCP"]
        mensagem = f"scoped:{contexto}:{documento}"
    else:
        mensagem = f"cpf:{digitos}"
    digest = hmac.new(chave.encode(), mensagem.encode(), hashlib.sha256).hexdigest()
    return f"hmac:{digest}"
