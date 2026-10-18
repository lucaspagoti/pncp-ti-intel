"""Cobertura e concordância da busca PNCP por termos contra o ARP (R3, D6).

A referência da lista de termos são as atas de TI vigentes do Compras ARP: outra base (Dados
Abertos), classificada pelo anexo da IN 05 no objeto ou no nome do item, ou pelos códigos do
catálogo, sem passar pelo índice de busca do PNCP. As duas fontes se cruzam por
`numero_controle_pncp`. Mede só a sobreposição (atas do SIASG publicadas no PNCP); não é
recall nacional. O anexo e a lista de termos são ambos listas de palavras: a concordância pelo
objeto não é independente e não substitui a precisão rotulada (a amostra no fim do relatório).

Só lê o banco; escreve `evals/pncp_busca_<data>.md`. Recusa rodar se a lista de termos mudou
depois da carga ativa da busca (o diagnóstico das perdas misturaria duas versões).

    python -m pncp_ti.fontes.pncp_busca_auditoria
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes.arp import FONTE as FONTE_ARP
from pncp_ti.fontes.arp_auditoria import _celula, no_universo
from pncp_ti.fontes.pncp_busca import FONTE as FONTE_BUSCA
from pncp_ti.fontes.pncp_busca import ID_PNCP_ATA, casa_termo, ler_termos

RAIZ_EVALS = Path(__file__).resolve().parents[3] / "evals"
AMOSTRA = 30
BASES = {
    "objeto": "pelo objeto (anexo da IN 05)",
    "item": "pelo nome do item (anexo da IN 05)",
    "catalogo": "pelos códigos do catálogo (CATMAT/CATSER)",
}
# `motivo_ti` do anexo da IN 05: "<grupo>:<palavra>@objeto" (ex.: "geral:informatica@objeto").
_PALAVRA_DO_ANEXO = re.compile(r"^[^:]+:(?P<palavra>[^@]+)@objeto$")
_LINK_PNCP = re.compile(r"https://pncp\.gov\.br/app/atas/\d{14}/\d{4}/\d+/\d+")
_MARKDOWN = re.compile(r"([\\`*_\[\]<>!#~])")

log = structlog.get_logger()


def base_do_motivo(motivo: str | None) -> str:
    """Como o ARP decidiu: códigos do catálogo, palavra do anexo no item ou no objeto."""
    motivo = motivo or ""
    if motivo.startswith(("catmat", "catser")):
        return "catalogo"
    return "item" if motivo.endswith("@item") else "objeto"


def termos_da_busca(motivo: str | None) -> list[str]:
    prefixo = "termo_pncp:"
    if not motivo or not motivo.startswith(prefixo):
        return []
    return [t for t in motivo[len(prefixo) :].split("|") if t]


def versao_termos(termos: Sequence[str]) -> str:
    """O mesmo hash que a carga da busca grava em `cargas.geracao._termos.sha256`."""
    return hashlib.sha256("\n".join(termos).encode()).hexdigest()[:12]


def _texto(valor: str | None, limite: int = 90) -> str:
    """Célula de texto de terceiros: CPF mascarado e Markdown/HTML inertes no `evals/`."""
    return _MARKDOWN.sub(r"\\\1", _celula(valor, limite))


def _link(valor: str | None) -> str:
    return valor if valor and _LINK_PNCP.fullmatch(valor) else ""


def _id(valor: str | None) -> str:
    return f"`{valor}`" if valor and ID_PNCP_ATA.fullmatch(valor) else _texto(valor, 40)


@dataclass(slots=True)
class Avaliacao:
    referencia: Counter[str] = field(default_factory=Counter)  # por base do motivo
    achadas: Counter[str] = field(default_factory=Counter)
    perdidas: list[Mapping[str, Any]] = field(default_factory=list)
    perdidas_com_termo: int = 0  # o objeto do ARP tem um termo; a busca não trouxe a ata
    palavras_sem_termo: Counter[str] = field(default_factory=Counter)
    # por termo: atas aceitas, quantas o ARP também tem e quantas o ARP classifica como TI
    por_termo: dict[str, list[int]] = field(default_factory=dict)
    na_sobreposicao: int = 0  # atas únicas da busca que o ARP também tem
    concordam: int = 0  # dessas, quantas o ARP classifica como TI
    fora_do_arp: list[Mapping[str, Any]] = field(default_factory=list)

    @property
    def cobertura(self) -> float:
        total = sum(self.referencia.values())
        return sum(self.achadas.values()) / total if total else 0.0


def avaliar(
    arp: Iterable[Mapping[str, Any]],
    busca: Iterable[Mapping[str, Any]],
    termos: Sequence[str],
    hoje: date,
) -> Avaliacao:
    resultado = Avaliacao()
    # Só o que a view pública mostraria: cancelada, futura ou vencida não conta como achada.
    busca_por_id = {
        b["numero_controle_pncp"]: b
        for b in busca
        if b["numero_controle_pncp"] and no_universo(b, hoje)
    }
    arp_por_id: dict[str, Mapping[str, Any]] = {}
    for a in arp:
        if a["numero_controle_pncp"]:
            arp_por_id[a["numero_controle_pncp"]] = a
        if not (a["is_ti"] and a["numero_controle_pncp"] and no_universo(a, hoje)):
            continue
        base = base_do_motivo(a["motivo_ti"])
        resultado.referencia[base] += 1
        if a["numero_controle_pncp"] in busca_por_id:
            resultado.achadas[base] += 1
            continue
        resultado.perdidas.append(a)
        if any(casa_termo(a["objeto"] or "", t) for t in termos):
            resultado.perdidas_com_termo += 1
        elif m := _PALAVRA_DO_ANEXO.match(a["motivo_ti"] or ""):
            resultado.palavras_sem_termo[m["palavra"]] += 1

    for controle, b in busca_por_id.items():
        par = arp_por_id.get(controle)
        ti = bool(par and par["is_ti"])
        resultado.na_sobreposicao += par is not None
        resultado.concordam += ti
        for termo in termos_da_busca(b["motivo_ti"]) or ["(sem termo)"]:
            contas = resultado.por_termo.setdefault(termo, [0, 0, 0])
            contas[0] += 1
            contas[1] += par is not None
            contas[2] += ti
        if par is None:
            resultado.fora_do_arp.append(b)
    return resultado


def _ordem_concordancia(par: tuple[str, list[int]]) -> tuple[float, str]:
    termo, (_, no_arp, ti) = par
    return (ti / no_arp if no_arp else 2.0, termo)


def relatorio(
    av: Avaliacao, hoje: date, data_cargas: str, versao: str, semente: int | None = None
) -> str:
    sorteio = random.Random(hoje.toordinal() if semente is None else semente)
    perdidas = sorteio.sample(av.perdidas, min(20, len(av.perdidas)))
    amostra = sorteio.sample(
        sorted(av.fora_do_arp, key=lambda b: b["numero_controle_pncp"]),
        min(AMOSTRA, len(av.fora_do_arp)),
    )
    linhas = [
        f"# Cobertura da busca PNCP contra o ARP — {hoje.strftime('%d/%m/%Y')}",
        "",
        f"Cargas ativas: {data_cargas}; lista de termos `{versao}`.",
        "Gerado por `python -m pncp_ti.fontes.pncp_busca_auditoria`.",
        "",
        "Referência: atas de TI vigentes do Compras ARP com `numero_controle_pncp`, classificadas",
        "sem o índice de busca do PNCP. Mede a sobreposição SIASG/PNCP; **não é recall nacional**",
        "e não cobre estados e municípios fora do SIASG. A busca entra com o mesmo filtro de",
        "vigência da view.",
        "",
        "## Cobertura da lista de termos",
        "",
        "| ARP classificou como TI | atas | achadas pela busca | cobertura |",
        "|---|---|---|---|",
        *(
            f"| {rotulo} | {av.referencia[b]} | {av.achadas[b]} | "
            f"{av.achadas[b] / av.referencia[b]:.1%} |"
            for b, rotulo in BASES.items()
            if av.referencia[b]
        ),
        f"| **total** | {sum(av.referencia.values())} | {sum(av.achadas.values())} | "
        f"**{av.cobertura:.1%}** |",
        "",
        f"Das {len(av.perdidas)} perdidas, {av.perdidas_com_termo} têm um termo da lista no",
        "objeto da ata (o PNCP indexa o objeto da **compra**, que pode ser outro, ou a ata não",
        "aparece como vigente na busca). As demais não têm nenhum termo: são lacunas da lista.",
        "",
        "### Palavras do anexo nas perdidas sem termo (candidatas a termo; o Lucas decide)",
        "",
        "| Palavra do anexo da IN 05 | atas perdidas |",
        "|---|---|",
        *(f"| {_texto(p, 60)} | {n} |" for p, n in av.palavras_sem_termo.most_common(15)),
        "",
        "Antes de virar termo, a palavra precisa passar pelo filtro de frase sem trazer ruído",
        "(ex.: `informatica` sozinha casa com mobiliário de informática).",
        "",
        "### Perdidas sorteadas (20)",
        "",
        "| Ata | Objeto (ARP) | Motivo no ARP | Link |",
        "|---|---|---|---|",
        *(
            f"| {_id(a['numero_controle_pncp'])} | {_texto(a['objeto'], 80)} | "
            f"{_texto(a['motivo_ti'], 50)} | {_link(a['link_origem'])} |"
            for a in perdidas
        ),
        "",
        "## Concordância por termo (proxy de precisão)",
        "",
        (
            f"Das {len(av.fora_do_arp) + av.na_sobreposicao} atas vigentes da busca, "
            f"{av.na_sobreposicao} também estão no ARP; o ARP classifica {av.concordam} delas "
            f"como TI ({av.concordam / av.na_sobreposicao:.1%})."
            if av.na_sobreposicao
            else "Nenhuma ata da busca está no ARP."
        ),
        "Não é precisão: o anexo da IN 05 e a lista de termos compartilham palavras (notebook,",
        "software, tecnologia da informação), então as duas fontes podem concordar no mesmo falso",
        "positivo. Serve para achar o termo a revisar primeiro: concordância baixa com muitas",
        "atas. Uma ata com vários termos conta em cada um na tabela e uma vez no total acima.",
        "",
        "| Termo | atas | no ARP | ARP diz TI | concordância |",
        "|---|---|---|---|---|",
        *(
            f"| {_texto(t, 50)} | {c[0]} | {c[1]} | {c[2]} | {c[2] / c[1]:.0%} |"
            if c[1]
            else f"| {_texto(t, 50)} | {c[0]} | 0 | 0 | - |"
            for t, c in sorted(av.por_termo.items(), key=_ordem_concordancia)
        ),
        "",
        f"## Amostra para rotular ({len(amostra)} atas só da busca, fora do ARP)",
        "",
        "Preencha a coluna Rótulo com TI ou NÃO; a precisão rotulada sai desta amostra.",
        "",
        "| Ata | Esfera/UF | Objeto | Termos | Link | Rótulo |",
        "|---|---|---|---|---|---|",
        *(
            f"| {_id(b['numero_controle_pncp'])} | "
            f"{_texto(b['esfera'], 20)}/{_texto(b['uf'], 4)} | {_texto(b['objeto'], 90)} | "
            f"{_texto(', '.join(termos_da_busca(b['motivo_ti'])), 40)} | "
            f"{_link(b['link_origem'])} |  |"
            for b in amostra
        ),
        "",
    ]
    return "\n".join(linhas)


async def principal() -> int:
    settings = get_settings()
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    conn = await conectar(settings)
    try:
        consultas = {}
        for fonte in (FONTE_ARP, FONTE_BUSCA):
            cur = await conn.execute(
                "SELECT a.numero_controle_pncp, a.is_ti, a.motivo_ti, a.objeto, a.link_origem, "
                "a.inicio, a.fim, a.vigente_na_origem, a.esfera, a.uf, c.data_referencia, "
                "c.geracao -> '_termos' ->> 'sha256' AS termos_sha256 "
                "FROM cargas c JOIN atas a ON a.carga_id = c.id WHERE c.fonte = %s AND c.ativa",
                (fonte,),
            )
            consultas[fonte] = await cur.fetchall()
    finally:
        await conn.close()
    if not consultas[FONTE_ARP] or not consultas[FONTE_BUSCA]:
        log.error("auditoria_busca_sem_carga_ativa")
        return 1
    termos = ler_termos()
    versao = versao_termos(termos)
    da_carga = consultas[FONTE_BUSCA][0]["termos_sha256"]
    if da_carga != versao:
        log.error("auditoria_busca_termos_divergentes", arquivo=versao, carga=da_carga)
        return 1
    av = avaliar(consultas[FONTE_ARP], consultas[FONTE_BUSCA], termos, hoje)
    data_cargas = ", ".join(
        f"{fonte} de {linhas[0]['data_referencia']}" for fonte, linhas in consultas.items()
    )
    RAIZ_EVALS.mkdir(exist_ok=True)
    destino = RAIZ_EVALS / f"pncp_busca_{hoje.strftime('%Y%m%d')}.md"
    destino.write_text(relatorio(av, hoje, data_cargas, versao), encoding="utf-8")
    log.info("auditoria_busca_ok", arquivo=str(destino), cobertura=round(av.cobertura, 4))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(principal()))


if __name__ == "__main__":
    main()
