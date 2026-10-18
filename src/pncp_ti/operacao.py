"""Alertas de incidente por fonte, com fila durável (ADR 0022 e 0027)."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import psycopg
from psycopg.rows import dict_row

from pncp_ti.config import get_settings, ingest_dsn
from pncp_ti.notificar import publicar

SP = ZoneInfo("America/Sao_Paulo")


def alertas(cargas: list[dict], agora: datetime, termo: str | None = None) -> list[tuple[str, str]]:
    """Avaliação pura; sem_mudanca não esconde a idade dos arquivos SIGA."""
    avisos = []
    for fonte in ("siga_rj", "compras_arp"):
        linhas = [c for c in cargas if c["fonte"] == fonte]
        recente = max(linhas, key=lambda c: c["iniciado_em"], default=None)
        ativa = next((c for c in linhas if c["ativa"]), None)
        if recente and recente["status"] == "falhou":
            avisos.append((f"{fonte}:falhou", f"{fonte}: última carga falhou; consulte cargas."))
        if not ativa:
            avisos.append((f"{fonte}:ausente", f"{fonte}: nenhuma carga ativa."))
            continue
        if fonte == "siga_rj":
            datas = [
                datetime.fromisoformat(a["last_modified"])
                for a in ativa["geracao"].values()
                if isinstance(a, dict) and a.get("last_modified")
            ]
            # Sem Last-Modified (carga por diretório), referência conservadora à meia-noite SP.
            referencia = (
                min(datas) if datas else datetime.combine(ativa["data_referencia"], time(), SP)
            )
        else:
            referencia = ativa["concluido_em"]
        if referencia is None or agora - referencia > timedelta(hours=48):
            avisos.append((f"{fonte}:velha", f"{fonte}: dados parados há mais de 48h."))
    if termo:
        pncp = [c for c in cargas if c["fonte"] == "pncp_busca"]
        recente = max(pncp, key=lambda c: c["iniciado_em"], default=None)
        if not recente or recente["status"] not in {"concluida", "sem_mudanca"}:
            avisos.append(("pncp:indisponivel", "PNCP: termo monitorado sem carga bem-sucedida."))
        elif agora - recente["concluido_em"] > timedelta(hours=48):
            avisos.append(("pncp:velha", "PNCP: medição do termo monitorado há mais de 48h."))
        else:
            # Gancho R3: contagens.resultados_por_termo = {termo: total}.
            total = recente["contagens"].get("resultados_por_termo", {}).get(termo)
            if type(total) is not int or total < 0:
                avisos.append(("pncp:sem_metrica", "PNCP: métrica do termo monitorado ausente."))
            elif total == 0:
                avisos.append(
                    ("pncp:zero", "PNCP: termo estável monitorado retornou 0 resultados.")
                )
    return avisos


async def enfileirar(conn, agora: datetime, termo: str | None = None) -> None:
    hoje = agora.astimezone(SP).date()
    # Apenas ativa e última tentativa de cada fonte; histórico grande não vai para memória.
    cargas = await (
        await conn.execute("""
        SELECT * FROM cargas WHERE ativa OR id IN (
            SELECT DISTINCT ON (fonte) id FROM cargas ORDER BY fonte, iniciado_em DESC, id
        )
    """)
    ).fetchall()
    for codigo, corpo in alertas(cargas, agora, termo):
        await conn.execute(
            "INSERT INTO notificacoes (chave, corpo) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (f"alerta:{hoje}:{codigo}", corpo),
        )
    # Digest de atas novas desativado (ADR 0027): WhatsApp só para incidentes.


async def entregar(conn, client: httpx.AsyncClient) -> int:
    pendentes = await (
        await conn.execute(
            # Digests antigos ainda pendentes nunca saem (ADR 0027).
            "SELECT chave, corpo FROM notificacoes WHERE enviado_em IS NULL "
            "AND chave NOT LIKE 'digest:%%' ORDER BY criado_em, chave"
        )
    ).fetchall()
    falhas = 0
    for item in pendentes:
        # Persistir tentativa antes do HTTP. A chave continua pendente em timeout/crash.
        await conn.execute(
            "UPDATE notificacoes SET tentativas = tentativas + 1 WHERE chave = %s",
            (item["chave"],),
        )
        await conn.commit()
        try:
            await publicar(item["corpo"], client)
        except Exception as exc:
            falhas += 1
            await conn.execute(
                "UPDATE notificacoes SET erro_tipo = %s WHERE chave = %s",
                (type(exc).__name__, item["chave"]),
            )
        else:
            await conn.execute(
                "UPDATE notificacoes SET enviado_em = now(), erro_tipo = NULL WHERE chave = %s",
                (item["chave"],),
            )
        await conn.commit()
    return falhas


async def executar(modo: str, unidade: str | None = None) -> int:
    # Timeout explícito e sem redirects/proxy herdado; não repetir POST automaticamente.
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        if modo == "falha":
            if not unidade or not re.fullmatch(r"pncp-ti-[a-zA-Z0-9_.@-]{1,100}", unidade):
                raise ValueError("unidade inválida")
            # OnFailure funciona mesmo com o Postgres indisponível.
            await publicar(f"Falha no serviço {unidade}; consulte journalctl --user.", client)
            return 0
        async with await psycopg.AsyncConnection.connect(
            ingest_dsn(get_settings()), row_factory=dict_row
        ) as conn:
            bloqueio = await (
                await conn.execute(
                    "SELECT pg_try_advisory_lock(hashtextextended('pncp-ti:operacao', 0)) AS ok"
                )
            ).fetchone()
            await conn.commit()
            if not bloqueio["ok"]:
                return 0
            if modo == "diaria":
                async with conn.transaction():
                    await enfileirar(
                        conn, datetime.now(SP), os.getenv("PNCP_TI_PNCP_TERMO") or None
                    )
            return int(bool(await entregar(conn, client)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modo", choices=("diaria", "reenviar", "falha"))
    parser.add_argument("--unidade")
    args = parser.parse_args()
    try:
        resultado = asyncio.run(executar(args.modo, args.unidade))
    except Exception as exc:
        print(f"Operação falhou: {type(exc).__name__}")
        resultado = 1
    raise SystemExit(resultado)


if __name__ == "__main__":
    main()
