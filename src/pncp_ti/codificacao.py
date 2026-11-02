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
# Segundo byte de `Ñ Ò Ó Ô Õ Ö ×` e de `Å`: em cp1252 é pontuação, que também pode seguir
# uma palavra legítima terminada em "Ã" (`MAÇÔ`). Ver `_ambigua`.
_PONTUACAO = set("‘’“”•–—…")
_ABRE = {"’": "‘", "”": "“"}
# Resíduo inequívoco depois do reparo (sequências que português legítimo não tem).
_MOJIBAKE = re.compile("Ã[©§£¡³ªº¢´µ¨ƒ‡°]|Â[ºª°]")
PASSADAS = 3  # texto codificado duas vezes precisa de mais de uma


def _ambigua(m: re.Match[str]) -> bool:
    """`Ã` + pontuação no fim de palavra é texto cp1252 legítimo, não UTF-8?

    `MACEIÃ“` e `PÃ“` são `MACEIÓ` e `PÓ`, o caso comum. Fica como está só com sinal de
    texto cp1252 legítimo: outra letra acentuada de verdade na mesma palavra (`MAÇÔ`) ou,
    para aspa de fechamento, a aspa de abertura correspondente antes na linha (`“IRMÔ`).
    """
    texto, inicio = m.string, m.start()
    segundo = m.group()[1]
    if texto[m.end() : m.end() + 1].isalpha():
        return False
    palavra = inicio
    while palavra > 0 and texto[palavra - 1].isalpha():
        palavra -= 1
    if any(
        not c.isascii() and c not in "ÂÃ" and c not in _CONTINUACAO for c in texto[palavra:inicio]
    ):
        return True
    if segundo in _ABRE:
        linha = texto.rfind("\n", 0, inicio) + 1
        return _ABRE[segundo] in texto[linha:inicio]
    return False


def _trocar(m: re.Match[str]) -> str:
    trecho = m.group()
    if len(trecho) == 2 and trecho[1] in _PONTUACAO and _ambigua(m):
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
