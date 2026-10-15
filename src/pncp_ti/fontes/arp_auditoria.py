"""Auditoria de recall da carga ARP por PDM de TI e amostra para conferência (ADR 0020).

Mede o furo conhecido do critério: ata de TI com objeto genérico não é candidata e seus itens
não são buscados. Para cada PDM do CATMAT grupo 70, consulta o endpoint de itens em lote
(`2_consultarARPItem`, `codigoPdm`) e cruza as atas encontradas com a carga ativa. Só lê o
banco; escreve `evals/arp_<data>.md`.

    python -m pncp_ti.fontes.arp_auditoria
"""

from __future__ import annotations

import asyncio
import random
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from compras_mcp.clients.dados_abertos import DadosAbertosClient
from compras_mcp.errors import ComprasError

from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes.arp import (
    FONTE,
    TENTATIVAS_HTTP,
    URL_BASE,
    _Orcamento,
    _pagina,
    carregar_catalogo,
)
from pncp_ti.fontes.arp_dados import validar_pagina
from pncp_ti.fontes.siga_csv import ErroValidacao
from pncp_ti.privacy import sanitizar

ROTA_ITENS = "/modulo-arp/2_consultarARPItem"
JANELA_DIAS = 365
ANOS_MAXIMOS = 5
RAIZ_EVALS = Path(__file__).resolve().parents[3] / "evals"

log = structlog.get_logger()


def _janelas(inicio: date, fim: date) -> list[tuple[date, date]]:
    resultado = []
    while inicio <= fim:
        final = min(inicio + timedelta(days=JANELA_DIAS), fim)
        resultado.append((inicio, final))
        inicio = final + timedelta(days=1)
    return resultado


def no_universo(ata: Mapping[str, Any], hoje: date) -> bool:
    """O mesmo filtro das views públicas (migração 0006): vigente na origem e no prazo hoje."""
    inicio = ata["inicio"]
    return (
        bool(ata["vigente_na_origem"]) and (inicio is None or inicio <= hoje) and ata["fim"] >= hoje
    )


def _celula(texto: str | None, limite: int = 90) -> str:
    # Texto de terceiros vai para `evals/` (versionado): CPF mascarado antes de tudo.
    texto = " ".join(str(sanitizar(texto or "")).split()).replace("|", "/")
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


async def principal() -> int:
    settings = get_settings()
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    conn = await conectar(settings)
    try:
        cur = await conn.execute(
            "SELECT a.id_origem, a.is_ti, a.motivo_ti, a.objeto, a.link_origem, a.inicio, "
            "a.fim, a.vigente_na_origem, c.data_referencia, c.contagens "
            "FROM cargas c JOIN atas a ON a.carga_id = c.id WHERE c.fonte = %s AND c.ativa",
            (FONTE,),
        )
        atas = {r["id_origem"]: r for r in await cur.fetchall()}
        if not atas:
            log.error("auditoria_sem_carga_ativa")
            return 1
        cur = await conn.execute(
            "SELECT a.status_origem, a.vigente_na_origem, count(*) n FROM cargas c "
            "JOIN atas a ON a.carga_id = c.id WHERE c.fonte = %s AND c.ativa "
            "GROUP BY 1, 2 ORDER BY 3 DESC",
            (FONTE,),
        )
        status = await cur.fetchall()
        cur = await conn.execute(
            "SELECT i.ata_id_origem, i.descricao, i.valor_unitario, i.valor_valido "
            "FROM cargas c JOIN ata_itens i ON i.carga_id = c.id "
            "WHERE c.fonte = %s AND c.ativa",
            (FONTE,),
        )
        itens_banco: dict[str, list] = defaultdict(list)
        for r in await cur.fetchall():
            itens_banco[r["ata_id_origem"]].append(r)
    finally:
        await conn.close()

    vigentes = {i: a for i, a in atas.items() if no_universo(a, hoje)}
    inicios = [a["inicio"] for a in vigentes.values() if a["inicio"]]
    primeiro = max(min(inicios), hoje - timedelta(days=365 * ANOS_MAXIMOS))
    orcamento = _Orcamento(settings.arp_requests_per_second, settings.arp_max_requisicoes)
    com_item_ti: dict[str, set[str]] = defaultdict(set)  # ata -> nomes de PDM de TI
    falhas = paginadas = 0
    async with DadosAbertosClient(
        base_url=URL_BASE, timeout=90.0, max_retries=TENTATIVAS_HTTP
    ) as client:
        catalogo = await carregar_catalogo(client, orcamento)
        for pdm in sorted(catalogo.pdms):
            for minimo, maximo in _janelas(primeiro, hoje):
                filtros = {
                    "codigoPdm": pdm,
                    "dataVigenciaInicialMin": minimo.isoformat(),
                    "dataVigenciaInicialMax": maximo.isoformat(),
                }
                pagina = 1
                try:
                    while True:
                        resposta = await _pagina(client, orcamento, ROTA_ITENS, pagina, **filtros)
                        registros, _, paginas = validar_pagina(resposta, pagina)
                        for r in registros:
                            ata = r.get("numeroControlePncpAta")
                            if ata in vigentes and r.get("itemExcluido") is not True:
                                com_item_ti[ata].add(str(r.get("nomePdm") or pdm))
                        if pagina >= paginas:
                            break
                        pagina += 1
                    paginadas += pagina > 1
                except ErroValidacao as exc:
                    if exc.tipo == "teto_requisicoes":
                        raise
                    falhas += 1
                    log.warning("auditoria_falha", pdm=pdm, erro=exc.tipo)
                except ComprasError as exc:
                    falhas += 1
                    log.warning("auditoria_falha", pdm=pdm, erro=type(exc).__name__)

    ti = {i for i, a in vigentes.items() if a["is_ti"]}
    achadas = set(com_item_ti)
    perdidas = sorted(achadas - ti)
    recall = len(achadas & ti) / len(achadas) if achadas else 0.0
    sorteio = random.Random(hoje.toordinal()).sample(sorted(ti), min(10, len(ti)))
    contagens = next(iter(atas.values()))["contagens"]
    data_carga = next(iter(atas.values()))["data_referencia"]

    linhas = [
        f"# Auditoria da carga ARP — {hoje.strftime('%d/%m/%Y')}",
        "",
        f"Carga ativa de {data_carga}. Gerado por `python -m pncp_ti.fontes.arp_auditoria`.",
        "",
        "## Números da carga",
        "",
        "| Contagem | Valor |",
        "|---|---|",
        *(f"| `{k}` | {v} |" for k, v in sorted(contagens.items())),
        "",
        "## Status de origem",
        "",
        "| `statusAta` | vigente na origem | atas |",
        "|---|---|---|",
        *(f"| {s['status_origem']} | {s['vigente_na_origem']} | {s['n']} |" for s in status),
        "",
        "## Recall por PDM de TI (CATMAT grupo 70)",
        "",
        f"- Atas vigentes com ao menos um item de PDM de TI (endpoint em lote): **{len(achadas)}**",
        f"- Dessas, classificadas como TI pela carga: **{len(achadas & ti)}**",
        (
            f"- **Recall medido: {recall:.1%}**; falsos negativos: **{len(perdidas)}**"
            if not falhas
            else f"- **INCONCLUSIVO**: {falhas} consultas falharam; recall parcial {recall:.1%}, "
            f"falsos negativos vistos: {len(perdidas)}"
        ),
        f"- Consultas com falha: {falhas}; janelas paginadas: {paginadas} (a paginação da API "
        "pode omitir registros, então o número de achadas é um piso)",
        "",
        "Mede só o recall de material de TI pelo catálogo; serviços de TI e atas cujo item não",
        "tem PDM ficam fora. Não é recall nacional.",
        "",
        "### Falsos negativos (até 50)",
        "",
        "| Ata | Objeto | PDMs de TI | Link |",
        "|---|---|---|---|",
        *(
            f"| `{i}` | {_celula(vigentes[i]['objeto'])} | "
            f"{_celula(', '.join(sorted(com_item_ti[i])), 60)} | {vigentes[i]['link_origem']} |"
            for i in perdidas[:50]
        ),
        "",
        "## Amostra para conferência manual (10 atas de TI)",
        "",
        "Conferir objeto, vigência e preço dos itens contra o link do PNCP.",
        "",
        "| Ata | Objeto | Motivo | Itens (preço válido) | Link |",
        "|---|---|---|---|---|",
        *(
            f"| `{i}` | {_celula(vigentes[i]['objeto'], 70)} | `{vigentes[i]['motivo_ti']}` | "
            f"{len(itens_banco[i])} ({sum(1 for x in itens_banco[i] if x['valor_valido'])}) | "
            f"{vigentes[i]['link_origem']} |"
            for i in sorteio
        ),
        "",
    ]
    RAIZ_EVALS.mkdir(exist_ok=True)
    destino = RAIZ_EVALS / f"arp_{hoje.strftime('%Y%m%d')}.md"
    destino.write_text("\n".join(linhas), encoding="utf-8")
    if falhas:
        log.error("auditoria_inconclusiva", arquivo=str(destino), falhas=falhas)
        return 1
    log.info("auditoria_ok", arquivo=str(destino), recall=round(recall, 4), perdidas=len(perdidas))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(principal()))


if __name__ == "__main__":
    main()
