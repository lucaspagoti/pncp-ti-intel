"""Auditoria de recall da carga ARP por PDM de TI e amostra para conferência (ADR 0020).

Mede o furo conhecido do critério: ata de TI com objeto genérico não é candidata e seus itens
não são buscados. Para cada PDM do CATMAT grupo 70, consulta o endpoint de itens em lote
(`2_consultarARPItem`, `codigoPdm`) e cruza as atas encontradas com a carga ativa. Só lê o
banco; escreve `evals/arp_<data>.md`.

    python -m pncp_ti.fontes.arp_auditoria
"""

from __future__ import annotations

import argparse
import asyncio
import random
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from compras_mcp.clients.dados_abertos import DadosAbertosClient

from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes.arp import (
    FONTE,
    TENTATIVAS_HTTP,
    URL_BASE,
    CacheVarredura,
    _Orcamento,
    carregar_catalogo,
    obter_varredura,
)
from pncp_ti.fontes.arp_regra import REGRA_PADRAO
from pncp_ti.privacy import sanitizar

RAIZ_EVALS = Path(__file__).resolve().parents[3] / "evals"

log = structlog.get_logger()


def no_universo(ata: Mapping[str, Any], hoje: date) -> bool:
    """O mesmo filtro das views públicas (migração 0006): vigente na origem e no prazo hoje."""
    inicio = ata["inicio"]
    return (
        bool(ata["vigente_na_origem"]) and (inicio is None or inicio <= hoje) and ata["fim"] >= hoje
    )


def _nomes_pdm(varredura: Any, ata: str) -> str:
    return ", ".join(sorted(varredura.nomes.get(p) or f"pdm {p}" for p in varredura.pdms(ata)))


def _celula(texto: str | None, limite: int = 90) -> str:
    # Texto de terceiros vai para `evals/` (versionado): CPF mascarado antes de tudo.
    texto = " ".join(str(sanitizar(texto or "")).split()).replace("|", "/")
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


async def principal(minutos: float | None = None) -> int:
    settings = get_settings()
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    conn = await conectar(settings)
    try:
        cur = await conn.execute(
            "SELECT a.id_origem, a.is_ti, a.motivo_ti, a.objeto, a.link_origem, a.inicio, "
            "a.fim, a.vigente_na_origem, a.quantidade_itens, c.data_referencia, c.contagens "
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
    # Mesma varredura e mesmo progresso semanal da carga: se ela já completou a semana, a
    # auditoria não gasta nenhuma requisição (sem prazo: termina a varredura que faltar).
    como_ata = {
        i: SimpleNamespace(inicio=a["inicio"], quantidade_itens=a["quantidade_itens"])
        for i, a in vigentes.items()
    }
    orcamento = _Orcamento(settings.arp_requests_per_second, settings.arp_max_requisicoes)
    async with DadosAbertosClient(
        base_url=URL_BASE, timeout=90.0, max_retries=TENTATIVAS_HTTP
    ) as client:
        catalogo = await carregar_catalogo(client, orcamento)
        varredura = await obter_varredura(
            client, orcamento, catalogo, como_ata, hoje, CacheVarredura.do_ciclo(hoje), minutos
        )
    falhas, incompletas = varredura.falhas + varredura.pendentes, varredura.incompletas

    quantidades = como_ata
    regra = REGRA_PADRAO
    ti = {i for i, a in vigentes.items() if a["is_ti"]}
    # Quem já tem linha na carga foi avaliado com os itens reais (TI ou incidental); só o que a
    # carga ainda não avaliou usa o corte aproximado pela contagem de itens da listagem.
    achadas = set(varredura.itens) & set(quantidades)
    avaliadas = {i for i in achadas if itens_banco.get(i)}  # a carga buscou os itens da ata
    ti_avaliadas = avaliadas & ti
    incidentais = {i for i in avaliadas if atas[i]["motivo_ti"] == "catalogo_incidental"}
    nao_avaliadas = {
        ata
        for ata in achadas - avaliadas
        if regra.passa(
            len(varredura.itens[ata]),
            quantidades[ata].quantidade_itens or 0,
            any(pdm in regra.pdms_centrais for pdm, _ in varredura.itens[ata]),
        )
    }
    no_corte = ti_avaliadas | nao_avaliadas
    perdidas = sorted(nao_avaliadas)
    recall = len(ti_avaliadas) / len(no_corte) if no_corte else 0.0
    recall_bruto = len(achadas & ti) / len(achadas) if achadas else 0.0
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
        f"  - já avaliadas pela carga com os itens reais: {len(avaliadas)} "
        f"(TI: {len(ti_avaliadas)}; **incidentais**, item de TI sem passar no corte: "
        f"{len(incidentais)})",
        f"  - ainda não avaliadas (carga anterior à varredura ou ciclo incompleto): "
        f"{len(achadas - avaliadas)}, das quais {len(nao_avaliadas)} passariam no corte pela "
        "contagem de itens da listagem (aproximação)",
        f"  - sem corte, classificadas como TI pela carga: {len(achadas & ti)} "
        f"({recall_bruto:.1%})",
        f"- Corte (proporção >= {regra.limiar_proporcao:.0%} dos itens ou PDM central, "
        f"`insumos/regra_ti_arp.json`, versão `{regra.versao()}`)",
        (
            f"- **Recall medido pelo critério: {recall:.1%}** (TI avaliadas contra TI avaliadas "
            f"mais as que passariam e a carga ainda não avaliou); falsos negativos: "
            f"**{len(perdidas)}**"
            if not falhas
            else f"- **INCONCLUSIVO**: {falhas} consultas falharam ou ficaram pendentes; recall "
            f"parcial {recall:.1%}, falsos negativos vistos: {len(perdidas)}"
        ),
        f"- Consultas com falha ou pendentes: {falhas}; janelas de 1 dia ainda paginadas: "
        f"{incompletas} (a API perde 1 registro por fronteira de página, então o número de "
        "achadas é um piso)",
        "",
        "Mede só o recall de material de TI pelo catálogo; serviços de TI e atas cujo item não",
        "tem PDM ficam fora. O corte usa `quantidadeItens` da listagem. Não é recall nacional.",
        "",
        "### Falsos negativos (até 50)",
        "",
        "| Ata | Objeto | PDMs de TI | Link |",
        "|---|---|---|---|",
        *(
            f"| `{i}` | {_celula(vigentes[i]['objeto'])} | "
            f"{_celula(_nomes_pdm(varredura, i), 60)} | {vigentes[i]['link_origem']} |"
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
    parser = argparse.ArgumentParser(description="Auditoria de recall da carga ARP por PDM.")
    parser.add_argument(
        "--minutos", type=float, help="orçamento de tempo da varredura; o progresso é guardado"
    )
    raise SystemExit(asyncio.run(principal(parser.parse_args().minutos)))


if __name__ == "__main__":
    main()
