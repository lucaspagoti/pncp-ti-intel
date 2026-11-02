"""Termos da busca (ADR 0036): palavra exata com plural, sinônimos revisados e marcação do item.

O radical do português junta palavras diferentes (`monitoramento` e `monitor` viram `monitor`). Para
ordenar pelo item principal, a busca também compara a palavra exata, sem radical, aceitando só
singular e plural. Tudo aqui é Python puro; o texto do usuário só chega ao SQL como parâmetro e,
na consulta exata, reduzido a `[a-z0-9]+`.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from markupsafe import Markup, escape

SINONIMOS = Path(__file__).resolve().parents[3] / "insumos" / "sinonimos_busca.txt"
MAX_ALTERNATIVAS = 3
PARADAS = frozenset(
    "a o as os de da do das dos e em no na nos nas para por com sem um uma ou ao aos".split()
)
_PALAVRA = re.compile(r"[a-z0-9]+")


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento, como o `unaccent(lower(...))` do banco."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def palavras(texto: str) -> list[str]:
    return [p for p in _PALAVRA.findall(normalizar(texto)) if p not in PARADAS]


def variantes(palavra: str) -> set[str]:
    """Singular e plural regulares do português, nos dois sentidos."""
    v = {palavra}
    if palavra.isdigit() or len(palavra) < 3:
        return v
    if palavra.endswith(("oes", "aes")):
        v.add(palavra[:-3] + "ao")
    elif palavra.endswith("ao"):
        v |= {palavra[:-2] + "oes", palavra[:-2] + "aes"}
    if palavra.endswith("eis"):
        v.add(palavra[:-3] + "el")
    elif palavra.endswith("ais"):
        v.add(palavra[:-3] + "al")
    elif palavra.endswith(("el", "al", "ol", "ul")):
        v.add(palavra[:-1] + "is")
    if palavra.endswith("ns"):
        v.add(palavra[:-2] + "m")
    elif palavra.endswith("m"):
        v.add(palavra[:-1] + "ns")
    if palavra.endswith("es") and palavra[-3:-2] in ("r", "z", "s"):
        v.add(palavra[:-2])
    elif palavra.endswith(("r", "z")):
        v.add(palavra + "es")
    elif palavra.endswith("s"):
        v.add(palavra[:-1])
    elif not palavra.endswith(("m", "l", "ao")):
        v.add(palavra + "s")
    return v


@lru_cache(maxsize=1)
def _grupos(caminho: Path = SINONIMOS) -> tuple[tuple[str, ...], ...]:
    """Grupos `termo = termo = termo`, uma linha por grupo; `#` comenta."""
    if not caminho.exists():
        return ()
    grupos = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        termos = tuple(t.strip() for t in linha.split("=") if t.strip())
        if len(termos) > 1:
            grupos.append(termos)
    return tuple(grupos)


def sinonimos(q: str) -> list[str]:
    """Outros termos do grupo quando a busca é exatamente um termo de um grupo (até 3)."""
    alvo = " ".join(palavras(q))
    for grupo in _grupos():
        normalizados = [" ".join(palavras(t)) for t in grupo]
        if alvo and alvo in normalizados:
            return [t for t, n in zip(grupo, normalizados, strict=True) if n != alvo][
                :MAX_ALTERNATIVAS
            ]
    return []


def consulta_exata(alternativas: list[str]) -> str | None:
    """`to_tsquery('simple')`: cada palavra (singular ou plural) de alguma alternativa."""
    clausulas = []
    for frase in alternativas:
        termos = palavras(frase)
        if termos:
            clausulas.append(
                " & ".join("(" + " | ".join(sorted(variantes(t))) + ")" for t in termos)
            )
    return " | ".join(f"({c})" for c in clausulas) or None


def marcar(texto: str | None, alternativas: list[str]) -> Markup:
    """Texto escapado com `<mark>` nas palavras buscadas; caixa alta da fonte vira frase."""
    if not texto:
        return Markup("")
    letras = [c for c in texto if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) >= 0.8 * len(letras):
        texto = texto.capitalize()
    alvo = {v for frase in alternativas for t in palavras(frase) for v in variantes(t)}
    partes = []
    for pedaco in re.split(r"(\w+)", texto):
        if pedaco and normalizar(pedaco) in alvo:
            partes.append(Markup("<mark>{}</mark>").format(pedaco))
        else:
            partes.append(escape(pedaco))
    return Markup("").join(partes)
