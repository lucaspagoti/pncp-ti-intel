"""Alertas de incidente por fonte, com fila durável (ADR 0022 e 0027)."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from datetime import date, datetime, time, timedelta
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
# Falha da carga com fonte e motivo (ADR 0032): lido de `cargas.erro_tipo`.
PRAZO_BANCO = 15.0  # segundos para ler `cargas` no OnFailure
FONTES_CARGA = {
    "siga_rj": "o SIGA RJ",
    "compras_arp": "o Compras.gov.br",
    "pncp_busca": "a busca PNCP",
}
_FORA_DO_PADRAO = "arquivo fora do padrão"
_RESPOSTA_ESTRANHA = "resposta fora do padrão"
_FORA_DO_AR = "fonte fora do ar"
MOTIVOS = {
    **dict.fromkeys(
        ("codificacao", "cabecalho", "colunas", "csv", "vazio", "geracao", "geracao_futura",
         "datas", "numeros", "orfaos", "conflito_ata", "cobertura_itens", "tamanho", "arquivo"),
        _FORA_DO_PADRAO,
    ),
    **dict.fromkeys(
        ("contrato", "envelope", "total_registros", "lote_inconsistente", "lote_incompleto",
         "listagem_inconsistente", "itens_incompletos", "itens_ausentes", "itens_inconsistentes",
         "conflito_id", "sem_id_excessivo", "pagina_vazia", "data_anomala"),
        _RESPOSTA_ESTRANHA,
    ),
    **dict.fromkeys(("rede", "http", "teto_requisicoes"), _FORA_DO_AR),
    "termos_falhos": "portal sem responder alguns termos há 14 dias",
    "sem_atas": "nenhuma ata devolvida",
    "queda_volume": "bem menos atas que ontem",
    "geracao_antiga": "arquivos da origem desatualizados",
    "concorrente": "outra atualização ainda rodando",
}  # fmt: skip


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
    defasado = _pncp_defasado(cargas, agora)
    if defasado:
        avisos.append(("pncp:defasada", defasado))
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


def _pncp_defasado(cargas: list[dict], agora: datetime) -> str | None:
    """Termos da busca PNCP que o portal não responde há 3 dias ou mais (ADR 0037).

    A carga publica reaproveitando as atas anteriores desses termos; o aviso diz quantos e
    há quanto tempo o mais antigo está parado, numa frase só (ADR 0030).
    """
    ativa = next((c for c in cargas if c["fonte"] == "pncp_busca" and c["ativa"]), None)
    defasados = (ativa or {}).get("contagens", {}).get("termos_defasados") or {}
    if not isinstance(defasados, dict) or not defasados:
        return None
    hoje = agora.astimezone(SP).date()
    try:
        dias = max((hoje - date.fromisoformat(d)).days for d in defasados.values())
    except (TypeError, ValueError):
        return None
    n = len(defasados)
    termos = "1 termo" if n == 1 else f"{n} termos"
    return f"a busca PNCP está com {termos} sem atualizar há {dias} dias (portal instável)"


def resumo(avisos: list[tuple[str, str]]) -> str | None:
    """Os avisos do dia numa frase só, ou None se não há nada a avisar."""
    if not avisos:
        return None
    return "Atas de TI: " + "; ".join(frase for _, frase in avisos) + "."


def _motivo(tipo: str | None) -> str | None:
    if not tipo:
        return None
    if tipo in MOTIVOS:
        return MOTIVOS[tipo]
    # Exceções fora de ErroValidacao gravam a classe: rede do httpx e erros HTTP do compras-mcp.
    if tipo.startswith("Compras") or tipo.endswith(("Timeout", "TimeoutError", "ConnectError")):
        return _FORA_DO_AR
    return None


def frase_carga(falhas: list[dict]) -> str:
    """A falha da carga numa frase: quais fontes e por quê, sem jargão (ADR 0032)."""
    if not falhas:
        return FALHAS["pncp-ti-carga.service"]
    ordem = list(FONTES_CARGA)
    falhas = sorted(falhas, key=lambda f: ordem.index(f["fonte"]) if f["fonte"] in ordem else 99)
    partes = []
    for falha in falhas:
        nome = FONTES_CARGA.get(falha["fonte"], falha["fonte"])
        motivo = _motivo(falha["erro_tipo"])
        partes.append((nome, motivo))
    if len(partes) == 1:
        nome, motivo = partes[0]
        detalhe = f" ({motivo})" if motivo else ""
        return f"{nome} não atualizou hoje{detalhe}; o site segue com os dados anteriores"
    itens = [f"{nome} ({motivo})" if motivo else nome for nome, motivo in partes]
    sujeito = ", ".join(itens[:-1]) + " e " + itens[-1]
    return f"{sujeito} não atualizaram hoje; o site segue com os dados anteriores"


async def _ler_falhas(inicio: datetime) -> list[dict]:
    async with await psycopg.AsyncConnection.connect(
        ingest_dsn(get_settings()), row_factory=dict_row, connect_timeout=5
    ) as conn:
        return await (
            await conn.execute(
                "SELECT DISTINCT ON (fonte) fonte, status, erro_tipo FROM cargas "
                "WHERE iniciado_em >= %s ORDER BY fonte, iniciado_em DESC, id",
                (inicio,),
            )
        ).fetchall()


async def falhas_de_hoje(agora: datetime) -> list[dict]:
    """Última carga de hoje de cada fonte, se falhou; vazio se o banco não responder."""
    inicio = datetime.combine(agora.astimezone(SP).date(), time(), SP)
    try:
        # Prazo para conexão e leitura juntas: sobra tempo para a frase genérica antes do
        # TimeoutStartSec=60 do OnFailure, mesmo com a leitura bloqueada.
        linhas = await asyncio.wait_for(_ler_falhas(inicio), PRAZO_BANCO)
    except Exception:
        # O OnFailure precisa avisar mesmo com o Postgres fora: cai na frase genérica.
        return []
    return [linha for linha in linhas if linha["status"] == "falhou"]


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
            if unidade == "pncp-ti-carga.service":
                frase = frase_carga(await falhas_de_hoje(datetime.now(SP)))
            else:
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
