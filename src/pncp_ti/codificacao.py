"""Reparo de texto UTF-8 que chegou lido como cp1252 (ADR 0031).

Sem I/O. O SIGA RJ publica cp1252, mas um valor gravado em UTF-8 na origem aparece como
"SaudÃ¡vel". Aqui cada sequência de bytes UTF-8 de 2 bytes (`Â`/`Ã` + continuação) ou
de pontuação tipográfica (`â€` + continuação) volta a ser o caractere original.

Bytes indefinidos em cp1252 (0x81, 0x8D, 0x8F, 0x90, 0x9D) chegam como *surrogate*
(`surrogateescape`): é o que `Á` e `Í` em UTF-8 viram num arquivo cp1252.
"""

from __future__ import annotations

import re

# Os 64 bytes de continuação UTF-8 (0x80-0xBF) como aparecem quando lidos em cp1252.
_CONTINUACAO = bytes(range(0x80, 0xC0)).decode("cp1252", "surrogateescape")
_CLASSE = "[" + re.escape(_CONTINUACAO) + "]"
_QUEBRADO = re.compile(f"[ÂÃ]{_CLASSE}|â[€‚]{_CLASSE}")
# Pontuação que pode seguir uma palavra legítima terminada em "Ã" ou "Â" (`MAÇÔ`): só
# conta como UTF-8 quando vem uma letra depois (`CONEXÃ•ES`).
_PONTUACAO = set("‘’“”•–—…‹›«»´¨ ­")
# Resíduo inequívoco depois do reparo (sequências que português legítimo não tem).
_MOJIBAKE = re.compile("Ã[©§£¡³ªº¢´µ¨ƒ‡°]|Â[ºª°]")
PASSADAS = 3  # texto codificado duas vezes precisa de mais de uma


def _trocar(m: re.Match[str]) -> str:
    trecho = m.group()
    if len(trecho) == 2 and trecho[1] in _PONTUACAO:
        seguinte = m.string[m.end() : m.end() + 1]
        if not seguinte.isalpha():
            return trecho
    try:
        return trecho.encode("cp1252", "surrogateescape").decode("utf-8")
    except UnicodeError:
        return trecho


def reparar(texto: str) -> tuple[str, int]:
    """Devolve o texto reparado e quantos trechos mudaram."""
    total = 0

    def trocar(m: re.Match[str]) -> str:
        nonlocal total
        novo = _trocar(m)
        total += novo != m.group()
        return novo

    for _ in range(PASSADAS):
        novo = _QUEBRADO.sub(trocar, texto)
        if novo == texto:
            break
        texto = novo
    return texto, total


def restante(texto: str) -> int:
    """Quantas sequências inequívocas de texto quebrado sobraram."""
    return sum(1 for _ in _MOJIBAKE.finditer(texto))
