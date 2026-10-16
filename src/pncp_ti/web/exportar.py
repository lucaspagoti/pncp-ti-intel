"""Exportação CSV com fórmulas neutralizadas (texto de terceiros nunca vira fórmula)."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from typing import Any

CABECALHO = [
    "fonte",
    "numero",
    "orgao",
    "unidade_gerenciadora",
    "objeto",
    "esfera",
    "uf",
    "municipio",
    "inicio",
    "fim",
    "n_itens",
    "preco_unitario_min",
    "preco_unitario_max",
    "link_origem",
]
_CAMPOS = {
    "preco_unitario_min": "preco_min",
    "preco_unitario_max": "preco_max",
}


def neutralizar(valor: Any) -> str:
    texto = "" if valor is None else str(valor)
    if texto.startswith(("\t", "\r", "\n")) or texto.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + texto
    return texto


def gerar_csv(linhas: list[Mapping[str, Any]]) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow(CABECALHO)
    for linha in linhas:
        escritor.writerow(neutralizar(linha.get(_CAMPOS.get(c, c))) for c in CABECALHO)
    return saida.getvalue()
