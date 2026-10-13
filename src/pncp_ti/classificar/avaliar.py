"""Precisão e recall do filtro de TI contra o rótulo final do Lucas (D6, ADR 0019).

Como a rotulagem é um censo das atas vigentes, as métricas valem para o SIGA, sem erro
amostral, e **não** se estendem a outras fontes.
"""

from __future__ import annotations

import argparse
import csv
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

EVALS = Path(__file__).resolve().parents[3] / "evals"
_TI = {"TI", "SIM", "S"}
_NAO_TI = {"NAO_TI", "NAO TI", "NAO", "N", "NAO-TI"}


class RotuloInvalido(ValueError):
    pass


def interpretar(valor: str) -> str | None:
    """`TI`, `NAO_TI` ou None (em branco). Aceita variações simples de digitação."""
    bruto = "".join(
        c
        for c in unicodedata.normalize("NFD", valor.strip().upper())
        if unicodedata.category(c) != "Mn"
    )
    if not bruto:
        return None
    if bruto in _TI:
        return "TI"
    if bruto in _NAO_TI:
        return "NAO_TI"
    raise RotuloInvalido(f"rótulo desconhecido: {valor!r}")


@dataclass(frozen=True, slots=True)
class Avaliacao:
    total: int
    verdadeiros_positivos: int
    falsos_positivos: list[dict[str, str]]
    falsos_negativos: list[dict[str, str]]
    verdadeiros_negativos: int
    sem_rotulo: int
    concordancia_pre: tuple[int, int]  # (concordam, comparadas)

    @property
    def precisao(self) -> float | None:
        base = self.verdadeiros_positivos + len(self.falsos_positivos)
        return self.verdadeiros_positivos / base if base else None

    @property
    def recall(self) -> float | None:
        base = self.verdadeiros_positivos + len(self.falsos_negativos)
        return self.verdadeiros_positivos / base if base else None


def avaliar(linhas: list[dict[str, str]]) -> Avaliacao:
    tp = tn = sem = concordam = comparadas = 0
    fp: list[dict[str, str]] = []
    fn: list[dict[str, str]] = []
    for linha in linhas:
        final = interpretar(linha.get("rotulo_lucas", ""))
        if final is None:
            sem += 1
            continue
        sistema = interpretar(linha["filtro_sistema"])
        if sistema == "TI" and final == "TI":
            tp += 1
        elif sistema == "TI":
            fp.append(linha)
        elif final == "TI":
            fn.append(linha)
        else:
            tn += 1
        pre = interpretar(linha.get("rotulo_pre", ""))
        if pre is not None:
            comparadas += 1
            concordam += pre == final
    return Avaliacao(len(linhas), tp, fp, fn, tn, sem, (concordam, comparadas))


def _pct(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor:.1%}"


def relatorio(av: Avaliacao, origem: Path, meta_precisao: float, meta_recall: float) -> str:
    def tabela(titulo: str, linhas: list[dict[str, str]]) -> list[str]:
        if not linhas:
            return [f"### {titulo}", "", "Nenhum.", ""]
        saida = [
            f"### {titulo} ({len(linhas)})",
            "",
            "| id | objeto | motivo do sistema |",
            "|---|---|---|",
        ]
        for linha in linhas:
            objeto = linha["objeto"].replace("|", "/")
            saida.append(f"| {linha['id_ata']} | {objeto} | {linha['motivo_sistema']} |")
        return [*saida, ""]

    ok_p = av.precisao is not None and av.precisao >= meta_precisao
    ok_r = av.recall is not None and av.recall >= meta_recall
    concordam, comparadas = av.concordancia_pre
    linhas = [
        f"# Avaliação do filtro de TI — SIGA RJ ({date.today():%d/%m/%Y})",
        "",
        f"Origem: `{origem.name}`. Censo das atas `Válida` com vigência cobrindo a data da carga; "
        "vale só para o SIGA.",
        "",
        "| Métrica | Valor | Meta (D6) | Atingida |",
        "|---|---|---|---|",
        f"| Precisão | {_pct(av.precisao)} | ≥ {meta_precisao:.0%} | {'sim' if ok_p else 'não'} |",
        f"| Recall | {_pct(av.recall)} | ≥ {meta_recall:.0%} | {'sim' if ok_r else 'não'} |",
        "",
        f"- Atas no censo: {av.total}; rotuladas: {av.total - av.sem_rotulo}; sem rótulo: "
        f"{av.sem_rotulo}.",
        f"- Verdadeiros positivos: {av.verdadeiros_positivos}; falsos positivos: "
        f"{len(av.falsos_positivos)}; falsos negativos: {len(av.falsos_negativos)}; "
        f"verdadeiros negativos: {av.verdadeiros_negativos}.",
        f"- Concordância entre a pré-rotulagem e o rótulo final: {concordam} de {comparadas}.",
        "",
    ]
    return "\n".join(
        [
            *linhas,
            *tabela("Falsos positivos (sistema marcou TI, rótulo final não)", av.falsos_positivos),
            *tabela(
                "Falsos negativos (sistema não marcou, rótulo final é TI)", av.falsos_negativos
            ),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Precisão/recall do filtro de TI (censo).")
    parser.add_argument("rotulos", type=Path, help="CSV de rotulagem com `rotulo_lucas` preenchido")
    parser.add_argument("--meta-precisao", type=float, default=0.85)
    parser.add_argument("--meta-recall", type=float, default=0.95)
    parser.add_argument("--saida", type=Path, default=None)
    args = parser.parse_args()
    with args.rotulos.open(newline="", encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    av = avaliar(linhas)
    if av.sem_rotulo:
        raise SystemExit(f"{av.sem_rotulo} atas sem `rotulo_lucas`; conclua a rotulagem.")
    saida = args.saida or EVALS / f"siga_{date.today():%Y%m%d}.md"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(
        relatorio(av, args.rotulos, args.meta_precisao, args.meta_recall), encoding="utf-8"
    )
    print(f"precisão={_pct(av.precisao)} recall={_pct(av.recall)} → {saida}")


if __name__ == "__main__":
    main()
