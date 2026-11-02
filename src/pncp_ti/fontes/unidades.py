"""Esfera, UF e município das atas do ARP pelo cadastro de unidades do PNCP (ADR 0034).

A API `modulo-arp` não traz esses campos. O id da ata (`numeroControlePncpAta`) começa pelo
CNPJ do órgão, e `codigoUnidadeGerenciadora` é o código da unidade no PNCP (15 de 15 na
sondagem de 02/11/2026). `GET /v1/orgaos/{cnpj}/unidades/{codigo}` dá os três campos; se a
unidade não existir (404), `GET /v1/orgaos/{cnpj}` dá ao menos a esfera.

O cadastro muda pouco: o resultado fica em `unidades_gerenciadoras` por `VALIDADE`. É um
enriquecimento: falha de rede ou de contrato deixa os campos nulos e nunca derruba a carga.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import psycopg
import structlog

from pncp_ti.ingest.rate_limit import LimitadorTaxa

URL_ORGAOS = "https://pncp.gov.br/api/pncp/v1/orgaos"
ESFERAS = {
    "F": "Federal",
    "E": "Estadual",
    "M": "Municipal",
    "D": "Distrital",
    "N": "Não se aplica",
}
VALIDADE = timedelta(days=30)
MAXIMO_CONSULTAS = 1500  # por carga; o resto fica para a próxima (o cache acumula)
REQUISICOES_POR_SEGUNDO = 4.0
TENTATIVAS = 3
ESPERA_BASE = 2.0
LIMITE_BYTES = 1024 * 1024  # uma unidade tem ~700 bytes

log = structlog.get_logger()

Chave = tuple[str, str]  # (cnpj, código da unidade)


@dataclass(frozen=True, slots=True)
class Unidade:
    esfera: str | None
    uf: str | None
    municipio: str | None


SEM_CADASTRO = Unidade(None, None, None)


class ErroContrato(ValueError):
    pass


class _Indisponivel(Exception):
    pass


def chave(id_ata: str, codigo_unidade: str) -> Chave | None:
    cnpj = id_ata[:14]
    if len(cnpj) == 14 and cnpj.isdigit() and codigo_unidade:
        return cnpj, codigo_unidade
    return None


def _esfera(orgao: Any) -> str | None:
    if not isinstance(orgao, dict) or "esferaId" not in orgao:
        raise ErroContrato("órgão sem esferaId")
    return ESFERAS.get(str(orgao["esferaId"]).upper())


def mapear_unidade(corpo: Any) -> Unidade:
    if not isinstance(corpo, dict) or "orgao" not in corpo or "municipio" not in corpo:
        raise ErroContrato("unidade sem orgao ou municipio")
    municipio = corpo["municipio"] or {}
    if not isinstance(municipio, dict):
        raise ErroContrato("municipio não é objeto")
    uf_obj = municipio.get("uf") or {}
    if not isinstance(uf_obj, dict):
        raise ErroContrato("municipio.uf não é objeto")
    uf = str(uf_obj.get("siglaUF") or "").strip().upper()
    nome = str(municipio.get("nome") or "").strip()
    return Unidade(_esfera(corpo["orgao"]), uf[:2] or None, nome[:200] or None)


def mapear_orgao(corpo: Any) -> Unidade:
    return Unidade(_esfera(corpo), None, None)


async def _pegar(client: httpx.AsyncClient, limitador: LimitadorTaxa, url: str) -> Any | None:
    """GET com retry; None em 404 (unidade ou órgão sem cadastro)."""
    ultimo = ""
    for tentativa in range(1, TENTATIVAS + 1):
        await limitador.aguardar()
        try:
            async with client.stream("GET", url) as resposta:
                if resposta.status_code == 404:
                    return None
                if resposta.status_code == 200:
                    corpo = bytearray()
                    async for bloco in resposta.aiter_bytes(1 << 16):
                        corpo.extend(bloco)
                        if len(corpo) > LIMITE_BYTES:
                            raise ErroContrato("resposta acima do limite")
                    return json.loads(corpo)
                ultimo = f"HTTP {resposta.status_code}"
            if resposta.status_code < 500 and resposta.status_code != 429:
                raise ErroContrato(f"respondeu {ultimo}")
        except (httpx.TransportError, json.JSONDecodeError) as exc:
            ultimo = type(exc).__name__
        if tentativa < TENTATIVAS:
            await asyncio.sleep(ESPERA_BASE * 2 ** (tentativa - 1))
    raise _Indisponivel(ultimo)


async def consultar(client: httpx.AsyncClient, limitador: LimitadorTaxa, c: Chave) -> Unidade:
    cnpj, codigo = c
    corpo = await _pegar(client, limitador, f"{URL_ORGAOS}/{cnpj}/unidades/{codigo}")
    if corpo is not None:
        return mapear_unidade(corpo)
    orgao = await _pegar(client, limitador, f"{URL_ORGAOS}/{cnpj}")
    return SEM_CADASTRO if orgao is None else mapear_orgao(orgao)


async def _do_cache(
    conn: psycopg.AsyncConnection, chaves: set[Chave]
) -> tuple[dict[Chave, Unidade], set[Chave]]:
    """Todas as unidades do cache e quais delas ainda estão dentro da validade."""
    linhas = await (
        await conn.execute(
            "SELECT cnpj, codigo, esfera, uf, municipio, consultado_em > now() - %s AS valida "
            "FROM unidades_gerenciadoras WHERE (cnpj, codigo) IN "
            "(SELECT * FROM unnest(%s::text[], %s::text[]))",
            (VALIDADE, [c[0] for c in chaves], [c[1] for c in chaves]),
        )
    ).fetchall()
    cache = {
        (r["cnpj"], r["codigo"]): Unidade(r["esfera"], r["uf"], r["municipio"]) for r in linhas
    }
    validas = {(r["cnpj"], r["codigo"]) for r in linhas if r["valida"]}
    return cache, validas


async def resolver(
    conn: psycopg.AsyncConnection,
    chaves: Iterable[Chave],
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[Chave, Unidade], dict[str, int]]:
    """Unidade de cada chave: cache válido, senão consulta; vencida e sem resposta usa o cache."""
    pedidas = set(chaves)
    cache, validas = await _do_cache(conn, pedidas)
    faltam = sorted(pedidas - validas)
    consultar_agora, adiadas = faltam[:MAXIMO_CONSULTAS], len(faltam[MAXIMO_CONSULTAS:])
    novas: dict[Chave, Unidade] = {}
    falhas = 0
    limitador = LimitadorTaxa(REQUISICOES_POR_SEGUNDO)
    proprio = client is None
    client = client or httpx.AsyncClient(timeout=20.0, headers={"Accept": "application/json"})
    try:
        for c in consultar_agora:
            try:
                novas[c] = await consultar(client, limitador, c)
            except (_Indisponivel, ErroContrato, ValueError, TypeError, AttributeError) as exc:
                falhas += 1
                if falhas == 1:
                    log.warning("unidades_consulta_falhou", tipo=type(exc).__name__, erro=str(exc))
    finally:
        if proprio:
            await client.aclose()
    if novas:
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO unidades_gerenciadoras (cnpj, codigo, esfera, uf, municipio) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (cnpj, codigo) DO UPDATE SET "
                "esfera = excluded.esfera, uf = excluded.uf, municipio = excluded.municipio, "
                "consultado_em = now()",
                [(c[0], c[1], u.esfera, u.uf, u.municipio) for c, u in novas.items()],
            )
    # Sempre fecha a transação, mesmo só com leitura: a publicação do ARP abre a própria
    # transação depois, e não pode virar um savepoint desta (QA-001).
    await conn.commit()
    resultado = {**cache, **novas}
    contagens = {
        "unidades": len(pedidas),
        "unidades_consultadas": len(novas),
        "unidades_falhas": falhas,
        "unidades_adiadas": adiadas,
        "unidades_sem_cadastro": sum(
            1 for c in pedidas if resultado.get(c, SEM_CADASTRO).uf is None
        ),
    }
    log.info("unidades_resolvidas", **contagens)
    return resultado, contagens
