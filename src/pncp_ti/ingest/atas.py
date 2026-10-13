"""Snapshot das atas de TI vigentes — fonte `/v1/atas` (ADR 0015)."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import structlog
from compras_mcp.clients.pncp import PNCPClient

from pncp_ti.classificar.regra import objeto_ata_tem_sinal_ti
from pncp_ti.ingest.executar import ingerir_janela
from pncp_ti.ingest.mapeadores import extrair_orgao_de_ata, mapear_ata
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.ingest.windows import Janela

log = structlog.get_logger(__name__)
ENTIDADE = "atas_ti_snapshot"
PATH = "/v1/atas"
N_AMOSTRA_DESCARTADAS = 200
RETENCAO_LOG_PAGINAS_DIAS = 30


class _AmostraDescartadas:
    def __init__(self, limite: int, seed: int) -> None:
        self.limite = limite
        self.random = random.Random(seed)
        self.total = 0
        self.linhas: list[dict] = []

    def incluir(self, payload: dict, referencia: date) -> bool:
        """Retém só atas vigentes; amostra aleatória das vigentes sem sinal de TI."""
        if payload.get("cancelado") is True:
            return False
        inicio = _data(payload.get("vigenciaInicio"))
        fim = _data(payload.get("vigenciaFim"))
        if inicio > referencia or fim < referencia:
            return False
        objeto = payload.get("objetoContratacao") or ""
        if objeto_ata_tem_sinal_ti(objeto):
            return True
        self.total += 1
        if len(self.linhas) < self.limite:
            self.linhas.append(payload)
        else:
            posicao = self.random.randrange(self.total)
            if posicao < self.limite:
                self.linhas[posicao] = payload
        return False


def _data(valor: object) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str) or len(valor) < 10:
        raise ValueError("vigência da ata ausente ou inválida")
    try:
        return date.fromisoformat(valor[:10])
    except ValueError as exc:
        raise ValueError("vigência da ata ausente ou inválida") from exc


def _mapear_snapshot(payload: dict, snapshot_id: UUID) -> dict:
    linha = mapear_ata(payload)
    controle = linha["numero_controle_pncp_ata"]
    linha["snapshot_id"] = snapshot_id
    linha["chave_snapshot"] = f"{snapshot_id}:{controle}"
    return linha


async def _iniciar_snapshot(
    conn: psycopg.AsyncConnection, referencia: date, snapshot_id: UUID
) -> None:
    lock = await (
        await conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended('pncp-ti-snapshot-atas', 0)) AS adquirido"
        )
    ).fetchone()
    if not lock["adquirido"]:
        await conn.rollback()
        raise RuntimeError("já existe um snapshot de atas em execução")
    try:
        # O resumo da execução fica em snapshots_atas_ti; os registros por
        # página são úteis para diagnóstico, mas não precisam crescer sem fim.
        await conn.execute(
            "DELETE FROM log_execucao_ingestao "
            "WHERE entidade = %s AND janela_fim < %s",
            (ENTIDADE, referencia - timedelta(days=RETENCAO_LOG_PAGINAS_DIAS)),
        )
        await conn.execute(
            "INSERT INTO snapshots_atas_ti (id, data_referencia, status) "
            "VALUES (%s, %s, 'em_andamento')",
            (snapshot_id, referencia),
        )
        await conn.commit()
    except BaseException:
        await conn.rollback()
        await conn.execute(
            "SELECT pg_advisory_unlock(hashtextextended('pncp-ti-snapshot-atas', 0))"
        )
        await conn.commit()
        raise


async def _guardar_descartadas(
    conn: psycopg.AsyncConnection, snapshot_id: UUID, linhas: list[dict]
) -> None:
    for payload in linhas:
        mapeada = mapear_ata(payload)
        controle = mapeada["numero_controle_pncp_ata"]
        await conn.execute(
            "INSERT INTO amostra_atas_descartadas "
            "(chave_snapshot, snapshot_id, numero_controle_pncp_ata, cnpj_orgao, "
            " objeto_contratacao, vigencia_inicio, vigencia_fim) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                f"{snapshot_id}:{controle}",
                snapshot_id,
                controle,
                mapeada["cnpj_orgao"],
                mapeada["objeto_contratacao"],
                mapeada["vigencia_inicio"],
                mapeada["vigencia_fim"],
            ),
        )


async def _publicar_snapshot(
    conn: psycopg.AsyncConnection,
    snapshot_id: UUID,
    amostra: _AmostraDescartadas,
    registros_lidos: int,
    candidatas_ti: int,
) -> None:
    async with conn.transaction():
        await _guardar_descartadas(conn, snapshot_id, amostra.linhas)
        await conn.execute("UPDATE snapshots_atas_ti SET ativo = false WHERE ativo")
        await conn.execute(
            "UPDATE snapshots_atas_ti SET status = 'concluido', ativo = true, "
            "registros_lidos = %s, candidatas_ti = %s, descartadas = %s, "
            "amostra_descartadas = %s, concluido_em = now() WHERE id = %s",
            (registros_lidos, candidatas_ti, amostra.total, len(amostra.linhas), snapshot_id),
        )
        # Mantém apenas o snapshot completo recém-publicado; a view segue vendo
        # o snapshot anterior até o commit desta transação.
        await conn.execute("DELETE FROM snapshots_atas_ti WHERE id <> %s", (snapshot_id,))
        await conn.execute(
            "DELETE FROM orgaos o WHERE NOT EXISTS "
            "(SELECT 1 FROM atas a WHERE a.cnpj_orgao = o.cnpj)"
        )


async def _falhar_snapshot(
    conn: psycopg.AsyncConnection, snapshot_id: UUID, erro: BaseException
) -> None:
    await conn.execute("DELETE FROM atas WHERE snapshot_id = %s", (snapshot_id,))
    await conn.execute(
        "DELETE FROM amostra_atas_descartadas WHERE snapshot_id = %s", (snapshot_id,)
    )
    await conn.execute(
        "DELETE FROM orgaos o WHERE NOT EXISTS (SELECT 1 FROM atas a WHERE a.cnpj_orgao = o.cnpj)"
    )
    await conn.execute(
        "UPDATE snapshots_atas_ti SET status = 'falhou', ativo = false, "
        "erro_tipo = %s, concluido_em = now() WHERE id = %s",
        (type(erro).__name__, snapshot_id),
    )
    await conn.commit()


async def ingerir_snapshot(
    conn: psycopg.AsyncConnection,
    cliente: PNCPClient,
    limitador: LimitadorTaxa,
    referencia: date,
    *,
    limite_amostra: int = N_AMOSTRA_DESCARTADAS,
) -> None:
    """Busca todas as atas vigentes numa data e publica o snapshot só ao concluir."""
    if limite_amostra < 1:
        raise ValueError("limite_amostra deve ser positivo")
    snapshot_id = uuid4()
    await _iniciar_snapshot(conn, referencia, snapshot_id)
    amostra = _AmostraDescartadas(limite_amostra, seed=snapshot_id.int)
    controles_vistos: set[str] = set()
    lidos = 0
    candidatas = 0

    def incluir(payload: dict) -> bool:
        nonlocal lidos, candidatas
        controle = payload.get("numeroControlePNCPAta")
        if not isinstance(controle, str) or not controle:
            raise ValueError("número de controle da ata ausente ou inválido")
        if controle in controles_vistos:
            return False
        controles_vistos.add(controle)
        lidos += 1
        aceita = amostra.incluir(payload, referencia)
        if aceita:
            candidatas += 1
        return aceita

    try:
        await ingerir_janela(
            conn,
            cliente,
            limitador,
            entidade=ENTIDADE,
            tabela="atas",
            chave="chave_snapshot",
            path=PATH,
            janela=Janela(referencia, referencia),
            filtros={},
            mapear=lambda payload: _mapear_snapshot(payload, snapshot_id),
            extrair_orgao=extrair_orgao_de_ata,
            incluir=incluir,
        )
        if not lidos:
            raise ValueError("snapshot nacional vazio; última carga preservada")
        await _publicar_snapshot(conn, snapshot_id, amostra, lidos, candidatas)
    except BaseException as exc:
        try:
            await conn.rollback()
            await _falhar_snapshot(conn, snapshot_id, exc)
        except Exception as limpeza_exc:
            # A falha original deve continuar identificável mesmo se o banco
            # ficar indisponível durante a recuperação.
            log.error("atas.snapshot_limpeza_falhou", erro_tipo=type(limpeza_exc).__name__)
        raise
    finally:
        try:
            await conn.rollback()
            await conn.execute(
                "SELECT pg_advisory_unlock(hashtextextended('pncp-ti-snapshot-atas', 0))"
            )
            await conn.commit()
        except Exception as exc:
            # Fechar a sessão também libera o advisory lock caso o SQL falhe.
            await conn.close()
            log.warning("atas.snapshot_unlock_falhou", erro_tipo=type(exc).__name__)

    log.info(
        "atas.snapshot_publicado",
        snapshot_id=str(snapshot_id),
        data_referencia=referencia.isoformat(),
        registros_lidos=lidos,
        candidatas_ti=candidatas,
        descartadas=amostra.total,
        amostra_descartadas=len(amostra.linhas),
    )
