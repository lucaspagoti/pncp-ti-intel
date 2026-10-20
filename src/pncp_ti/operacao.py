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
NOMES = {"siga_rj": "SIGA RJ", "compras_arp": "Compras.gov.br"}
# Uma frase por serviço, em português simples (o Lucas lê no WhatsApp, sem terminal).
FALHAS = {
    "pncp-ti-carga.service": "a atualização de hoje falhou; o site segue com os dados anteriores",
    "pncp-ti-web.service": "o site parou de funcionar",
    "pncp-ti-backup.service": "o backup de hoje falhou",
    "pncp-ti-operacao.service": "a verificação diária falhou",
}


def alertas(cargas: list[dict], agora: datetime, termo: str | None = None) -> list[tuple[str, str]]:
    """Avaliação pura; sem_mudanca não esconde a idade dos arquivos SIGA.

    Carga que falhou já foi avisada de madrugada pelo OnFailure da carga; aqui só entra o que
    ele não vê: dados parados, fonte sem dados e o termo estável zerado (ADR 0027).
    """
    avisos = []
    for fonte in ("siga_rj", "compras_arp"):
        nome = NOMES[fonte]
        ativa = next((c for c in cargas if c["fonte"] == fonte and c["ativa"]), None)
        if not ativa:
            avisos.append((f"{fonte}:ausente", f"{nome} sem dados"))
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
            avisos.append((f"{fonte}:velha", f"{nome} sem atualizar há mais de 2 dias"))
    if termo:
        pncp = [c for c in cargas if c["fonte"] == "pncp_busca"]
        recente = max(
            (c for c in pncp if c["status"] in {"concluida", "sem_mudanca"}),
            key=lambda c: c["iniciado_em"],
            default=None,
        )
        if recente is None or agora - recente["concluido_em"] > timedelta(hours=48):
            avisos.append(("pncp:velha", "busca PNCP sem atualizar há mais de 2 dias"))
        else:
            # Gancho R3: contagens.resultados_por_termo = {termo: total}. Termo ausente é termo
            # que não respondeu hoje e reaproveitou a carga (ADR 0028), não incidente.
            total = recente["contagens"].get("resultados_por_termo", {}).get(termo)
            if type(total) is int and total == 0:
                avisos.append(
                    (
                        "pncp:zero",
                        f'busca PNCP voltou vazia para "{termo}"; o portal pode ter mudado',
                    )
                )
    return avisos


def resumo(avisos: list[tuple[str, str]]) -> str | None:
    """Os avisos do dia numa frase só, ou None se não há nada a avisar."""
    if not avisos:
        return None
    return "Atas de TI: " + "; ".join(frase for _, frase in avisos) + "."


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
    corpo = resumo(alertas(cargas, agora, termo))
    if corpo:
        # Uma mensagem por dia, no máximo.
        await conn.execute(
            "INSERT INTO notificacoes (chave, corpo) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (f"alerta:{hoje}:resumo", corpo),
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
            frase = FALHAS.get(unidade, f"o serviço {unidade} falhou")
            await publicar(f"Atas de TI: {frase}.", client)
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
