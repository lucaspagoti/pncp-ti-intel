"""Carga diária das atas vigentes do Compras.gov.br, módulo ARP (ADR 0020).

Fluxo: lista as atas vigentes (3 janelas de ≤ 365 dias) → carrega o catálogo de TI
(CATMAT grupo 70 e classes CATSER) → busca os itens só das atas candidatas → classifica
(anexo da IN 05 ou catálogo) → grava numa carga nova e troca a ativa numa única
transação. Falha em qualquer etapa deixa a carga anterior visível (padrão da R1).

    python -m pncp_ti.fontes.arp             # lista, busca itens e carrega
    python -m pncp_ti.fontes.arp --validar   # idem, sem gravar no banco
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import structlog
from compras_mcp.clients.dados_abertos import DadosAbertosClient
from compras_mcp.errors import ComprasError

from pncp_ti.classificar.in05 import versao_regra
from pncp_ti.classificar.regra import CATMAT_GRUPO_TI, CATSER_CLASSES_TI
from pncp_ti.config import Settings, get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes.arp_dados import (
    CAMPOS_ATA,
    CAMPOS_ITEM,
    AtaArp,
    CatalogoTI,
    ItemArp,
    decidir_ata,
    e_candidata,
    mapear_ata,
    mapear_item,
    validar_contrato,
    validar_pagina,
)
from pncp_ti.fontes.siga import _copiar, _registrar_falha, tentar_trava_sessao
from pncp_ti.fontes.siga_csv import ErroValidacao
from pncp_ti.ingest.rate_limit import LimitadorTaxa

FONTE = "compras_arp"
CHAVE_TRAVA = "carga:compras_arp"
URL_BASE = "https://dadosabertos.compras.gov.br"
ROTA_ATAS = "/modulo-arp/1.2_consultarARP_FimVigencia"
ROTA_ITENS_ATA = "/modulo-arp/2.1_consultarARPItem_Id"
ROTA_PDM = "/modulo-material/3_consultarPdmMaterial"
ROTA_SERVICOS = "/modulo-servico/6_consultarItemServico"

TAMANHO_PAGINA = 500
JANELA_DIAS = 365  # limite da API para dataVigenciaFinalMin/Max
JANELAS = 3
ASSINATURA_MINIMA = date(2000, 1, 1)
CONCORRENCIA = 2
TENTATIVAS_HTTP = 6  # o 429 da API pede ~36 s de espera; o cliente respeita o Retry-After
PISO_ATAS = 0.5
PISO_ITENS = 0.7
TOLERANCIA_TOTAL = 0.01  # |atas únicas − totalRegistros| em relação ao declarado
LIMITE_SEM_ITEM = 0.05  # candidatas sem item (inclui falhas de busca)

RAIZ_CACHE = Path(__file__).resolve().parents[3] / "data" / "arp"

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    carga_id: UUID
    status: str  # concluida
    contagens: dict[str, int]


class _Orcamento:
    """Taxa e teto de requisições, compartilhados entre as tarefas concorrentes."""

    def __init__(self, por_segundo: float, teto: int) -> None:
        self._limitador = LimitadorTaxa(por_segundo)
        self._trava = asyncio.Lock()
        self._teto = teto
        self.requisicoes = 0

    async def pedir(self) -> None:
        async with self._trava:
            if self.requisicoes >= self._teto:
                raise ErroValidacao("teto_requisicoes", f"teto de {self._teto} requisições")
            self.requisicoes += 1
            await self._limitador.aguardar()


def janelas(hoje: date) -> list[tuple[date, date]]:
    inicio = hoje
    resultado = []
    for _ in range(JANELAS):
        fim = inicio + timedelta(days=JANELA_DIAS)
        resultado.append((inicio, fim))
        inicio = fim + timedelta(days=1)
    return resultado


async def _pagina(
    client: DadosAbertosClient, orcamento: _Orcamento, rota: str, pagina: int, **filtros: Any
) -> dict[str, Any]:
    await orcamento.pedir()
    return await client.list_resource(rota, pagina=pagina, tamanho_pagina=TAMANHO_PAGINA, **filtros)


async def listar_atas(
    client: DadosAbertosClient, orcamento: _Orcamento, hoje: date
) -> tuple[dict[str, AtaArp], int, int]:
    """Todas as atas com fim de vigência de hoje em diante: `(atas, declarado, paginadas)`.

    A API pagina por offset sem desempate estável: numa janela de duas semanas, 682 de 6.979
    registros vieram repetidos e outros 682 nunca vieram (13/10/2026). Por isso a janela é
    dividida até caber numa página só, primeiro pelo fim da vigência e, num dia cheio, pela data
    de assinatura. Só se nem isso couber a janela é paginada (`paginadas`, risco de perda).
    """
    atas: dict[str, AtaArp] = {}
    declarado = 0
    paginadas = 0
    semaforo = asyncio.Semaphore(CONCORRENCIA)

    async def consultar(filtros: dict[str, str], pagina: int = 1):
        async with semaforo:
            resposta = await _pagina(client, orcamento, ROTA_ATAS, pagina, **filtros)
        return validar_pagina(resposta, pagina)

    def guardar(registros: list[dict[str, Any]]) -> None:
        validar_contrato(registros, CAMPOS_ATA)
        for bruto in registros:
            ata = mapear_ata(bruto, hoje)
            if ata is not None:
                atas[ata.id_origem] = ata

    async def paginar(filtros: dict[str, str], primeira: list[dict[str, Any]], paginas: int):
        nonlocal paginadas
        paginadas += 1
        log.warning("arp_janela_paginada", paginas=paginas, **filtros)
        guardar(primeira)
        for pagina in range(2, paginas + 1):
            registros, _, _ = await consultar(filtros, pagina)
            guardar(registros)

    async def janela(fim: tuple[date, date], assinatura: tuple[date, date] | None) -> int:
        filtros = {
            "dataVigenciaFinalMin": fim[0].isoformat(),
            "dataVigenciaFinalMax": fim[1].isoformat(),
        }
        if assinatura:
            filtros["dataAssinaturaInicial"] = assinatura[0].isoformat()
            filtros["dataAssinaturaFinal"] = assinatura[1].isoformat()
        registros, total, paginas = await consultar(filtros)
        if paginas <= 1:
            guardar(registros)
            return total
        if fim[0] < fim[1]:
            meio = fim[0] + (fim[1] - fim[0]) // 2
            partes = [
                janela((fim[0], meio), assinatura),
                janela((meio + timedelta(days=1), fim[1]), assinatura),
            ]
        else:
            faixa = assinatura or (ASSINATURA_MINIMA, hoje)
            if faixa[0] >= faixa[1]:
                await paginar(filtros, registros, paginas)
                return total
            meio = faixa[0] + (faixa[1] - faixa[0]) // 2
            partes = [
                janela(fim, (faixa[0], meio)),
                janela(fim, (meio + timedelta(days=1), faixa[1])),
            ]
        soma = sum(await asyncio.gather(*partes))
        if soma != total:
            # Ex.: ata sem data de assinatura some do filtro. Pagina a janela inteira.
            await paginar(filtros, registros, paginas)
        return total

    for minimo, maximo in janelas(hoje):
        declarado += await janela((minimo, maximo), None)
    return atas, declarado, paginadas


async def carregar_catalogo(client: DadosAbertosClient, orcamento: _Orcamento) -> CatalogoTI:
    """PDMs do CATMAT grupo 70 e serviços das classes CATSER de TI (códigos de `regra.py`)."""
    pdms: set[int] = set()
    pagina = 1
    while True:
        resposta = await _pagina(client, orcamento, ROTA_PDM, pagina, codigoGrupo=CATMAT_GRUPO_TI)
        registros, _, paginas = validar_pagina(resposta, pagina)
        validar_contrato(registros, ("codigoPdm",))
        pdms.update(int(r["codigoPdm"]) for r in registros if r.get("codigoPdm") is not None)
        if pagina >= paginas:
            break
        pagina += 1
    servicos: dict[int, int] = {}
    for classe in sorted(CATSER_CLASSES_TI):
        pagina = 1
        while True:
            resposta = await _pagina(client, orcamento, ROTA_SERVICOS, pagina, codigoClasse=classe)
            registros, _, paginas = validar_pagina(resposta, pagina)
            validar_contrato(registros, ("codigoServico",))
            for r in registros:
                if r.get("codigoServico") is not None:
                    servicos[int(r["codigoServico"])] = classe
            if pagina >= paginas:
                break
            pagina += 1
    if not pdms or not servicos:
        raise ErroValidacao("catalogo", "catálogo de TI vazio (PDMs ou serviços)")
    return CatalogoTI(pdms=frozenset(pdms), servicos=servicos)


async def _itens_da_ata(
    client: DadosAbertosClient, orcamento: _Orcamento, ata_id: str
) -> list[ItemArp]:
    itens: list[ItemArp] = []
    pagina = 1
    while True:
        resposta = await _pagina(
            client, orcamento, ROTA_ITENS_ATA, pagina, numeroControlePncpAta=ata_id
        )
        registros, _, paginas = validar_pagina(resposta, pagina)
        validar_contrato(registros, CAMPOS_ITEM)
        for bruto in registros:
            item = mapear_item(bruto)
            if item is not None and item.ata_id_origem == ata_id:
                itens.append(item)
        if pagina >= paginas:
            return itens
        pagina += 1


class CacheItens:
    """Checkpoint em disco dos itens já buscados no dia (uma linha JSON por ata).

    Se a carga falhar depois de 1 h de busca, a próxima tentativa do mesmo dia só busca o que
    falta. Guarda o item já mapeado: identidade HMAC e texto mascarado, nunca o CPF bruto.
    """

    def __init__(self, caminho: Path, anterior: Path | None = None) -> None:
        self.caminho = caminho
        self.anterior = anterior  # tentativa que virou a meia-noite reaproveita a véspera

    @classmethod
    def do_dia(cls, hoje: date, raiz: Path = RAIZ_CACHE) -> CacheItens:
        raiz.mkdir(parents=True, exist_ok=True, mode=0o700)
        vespera = hoje - timedelta(days=1)
        return cls(raiz / f"itens-{hoje.isoformat()}.jsonl", raiz / f"itens-{vespera}.jsonl")

    def ler(self) -> dict[str, list[ItemArp]]:
        lidos: dict[str, list[ItemArp]] = {}
        for caminho in (self.anterior, self.caminho):
            if caminho is None or not caminho.is_file():
                continue
            with caminho.open(encoding="utf-8") as arquivo:
                for linha in arquivo:
                    try:
                        registro = json.loads(linha)
                        itens = [_item_de_json(i) for i in registro["itens"]]
                    except (ValueError, KeyError, TypeError):
                        continue  # linha truncada por queda no meio da escrita
                    lidos[registro["ata"]] = itens
        return lidos

    def gravar(self, ata_id: str, itens: list[ItemArp]) -> None:
        linha = json.dumps({"ata": ata_id, "itens": [asdict(i) for i in itens]}, default=str)
        novo = not self.caminho.exists()
        with self.caminho.open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")
        if novo:
            self.caminho.chmod(0o600)

    def limpar_antigos(self) -> None:
        for antigo in self.caminho.parent.glob("itens-*.jsonl"):
            if antigo != self.caminho:
                antigo.unlink(missing_ok=True)


_DECIMAIS = ("quantidade", "valor_unitario", "quantidade_empenhada", "maximo_adesao")


def _item_de_json(dados: dict[str, Any]) -> ItemArp:
    for campo in _DECIMAIS:
        if dados.get(campo) is not None:
            dados[campo] = Decimal(dados[campo])
    return ItemArp(**dados)


async def buscar_itens(
    client: DadosAbertosClient,
    orcamento: _Orcamento,
    ids: Sequence[str],
    ao_buscar: Callable[[str, list[ItemArp]], None] | None = None,
) -> tuple[dict[str, list[ItemArp]], int]:
    """Itens por ata, com concorrência limitada. Devolve `(itens_por_ata, falhas)`.

    Falha de rede ou resposta ruim numa ata vira "sem item" (contada); o chamador decide se
    usa os itens da carga anterior. Estouro do teto ou erro do programa cancela as demais.
    """
    semaforo = asyncio.Semaphore(CONCORRENCIA)
    resultado: dict[str, list[ItemArp]] = {}
    falhas = 0

    async def uma(ata_id: str) -> None:
        nonlocal falhas
        async with semaforo:
            try:
                resultado[ata_id] = await _itens_da_ata(client, orcamento, ata_id)
                if ao_buscar is not None:
                    ao_buscar(ata_id, resultado[ata_id])
            except ErroValidacao as exc:
                if exc.tipo == "teto_requisicoes":
                    raise
                falhas += 1
                log.warning("arp_itens_falha", ata=ata_id, tipo=exc.tipo)
            except ComprasError as exc:
                falhas += 1
                log.warning("arp_itens_falha", ata=ata_id, tipo=type(exc).__name__)

    async with asyncio.TaskGroup() as grupo:
        for ata_id in ids:
            grupo.create_task(uma(ata_id))
    return resultado, falhas


def validar_total(atas: Mapping[str, AtaArp], declarado: int) -> None:
    if not atas:
        raise ErroValidacao("sem_atas", "a API não devolveu nenhuma ata vigente")
    if declarado and abs(len(atas) - declarado) > TOLERANCIA_TOTAL * declarado:
        raise ErroValidacao(
            "total_registros", f"{len(atas)} atas únicas contra {declarado} declaradas"
        )


@dataclass(slots=True)
class Preparado:
    atas: list[AtaArp]
    itens: list[ItemArp]
    decisoes: dict[str, tuple[bool, str]]
    contagens: dict[str, int]


def preparar(
    atas: Mapping[str, AtaArp],
    itens_por_ata: Mapping[str, list[ItemArp]],
    candidatas: Sequence[str],
    falhas: int,
    declarado: int,
    catalogo: CatalogoTI,
) -> Preparado:
    """Valida o conjunto e classifica; sem rede nem banco."""
    validar_total(atas, declarado)
    sem_item = [a for a in candidatas if not itens_por_ata.get(a)]
    if candidatas and len(sem_item) > LIMITE_SEM_ITEM * len(candidatas):
        raise ErroValidacao(
            "itens_ausentes", f"{len(sem_item)} de {len(candidatas)} candidatas sem item"
        )

    itens: dict[str, ItemArp] = {}
    decisoes: dict[str, tuple[bool, str]] = {}
    for id_origem, ata in atas.items():
        do_ata = itens_por_ata.get(id_origem, [])
        for item in do_ata:
            itens[item.chave] = item
        decisao = decidir_ata(ata.objeto, do_ata, catalogo)
        decisoes[id_origem] = (decisao.is_ti, decisao.motivo)

    contagens = {
        "atas_unicas": len(atas),
        "atas_declaradas": declarado,
        "atas_candidatas": len(candidatas),
        "candidatas_sem_item": len(sem_item),
        "falhas_busca_itens": falhas,
        "itens_gravados": len(itens),
        "atas_ti": sum(1 for ti, _ in decisoes.values() if ti),
        "atas_vigentes_ti": sum(
            1 for i, a in atas.items() if a.vigente_na_origem and decisoes[i][0]
        ),
    }
    return Preparado(list(atas.values()), list(itens.values()), decisoes, contagens)


def _geracao(
    atas: Mapping[str, AtaArp], catalogo: CatalogoTI, declarado: int
) -> dict[str, dict[str, object]]:
    resumo = hashlib.sha256()
    for id_origem in sorted(atas):
        resumo.update(f"{id_origem}\x1f{atas[id_origem].atualizado_em}\x1e".encode())
    return {
        "atas": {"declarado": declarado, "unicas": len(atas), "sha256": resumo.hexdigest()},
        "_regra": {"versao": versao_regra(), "catalogo": catalogo.versao()},
    }


async def _publicar(
    conn: psycopg.AsyncConnection,
    preparado: Preparado,
    geracao: dict[str, dict[str, object]],
    carga_id: UUID,
    hoje: date,
) -> ResultadoCarga:
    contagens = preparado.contagens
    async with conn.transaction():
        bloqueio = await (
            await conn.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS ok", (CHAVE_TRAVA,)
            )
        ).fetchone()
        if not bloqueio["ok"]:
            raise ErroValidacao("concorrente", "outra carga do Compras ARP está em andamento")

        ativa = await (
            await conn.execute(
                "SELECT id, contagens, data_referencia FROM cargas WHERE fonte = %s AND ativa",
                (FONTE,),
            )
        ).fetchone()
        if ativa:
            if hoje < ativa["data_referencia"]:
                raise ErroValidacao(
                    "geracao_antiga",
                    f"data {hoje} anterior à carga ativa ({ativa['data_referencia']})",
                )
            for chave, piso in (("atas_unicas", PISO_ATAS), ("itens_gravados", PISO_ITENS)):
                anteriores = int(ativa["contagens"].get(chave, 0))
                if anteriores and contagens[chave] < piso * anteriores:
                    raise ErroValidacao(
                        "queda_volume",
                        f"{chave}: {contagens[chave]} contra {anteriores} na carga ativa",
                    )

        await conn.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status, geracao) "
            "VALUES (%s, %s, %s, 'em_andamento', %s)",
            (carga_id, FONTE, hoje, json.dumps(geracao)),
        )
        await _copiar(
            conn,
            "COPY atas (carga_id, id_origem, numero, unidade_gerenciadora, objeto, licitacao, "
            "inicio, fim, criterio_julgamento, status_origem, processos, is_ti, motivo_ti, "
            "vigente_na_origem, numero_controle_pncp, link_origem, orgao, valor_total, "
            "quantidade_itens, atualizado_origem) FROM STDIN",
            (
                (
                    carga_id,
                    a.id_origem,
                    a.numero,
                    a.unidade_gerenciadora,
                    a.objeto,
                    a.licitacao,
                    a.inicio,
                    a.fim,
                    None,
                    a.status_origem,
                    [],
                    *preparado.decisoes[a.id_origem],
                    a.vigente_na_origem,
                    a.id_origem,
                    a.link_origem,
                    a.orgao,
                    a.valor_total,
                    a.quantidade_itens,
                    a.atualizado_em,
                )
                for a in preparado.atas
            ),
        )
        await _copiar(
            conn,
            "COPY ata_itens (carga_id, chave, ata_id_origem, id_item, descricao, nome_catalogo, "
            "id_fornecedor, fornecedor, quantidade, valor_unitario, taxa_pct, valor_valido, "
            "tipo_item, codigo_catalogo, codigo_pdm, nome_pdm, quantidade_empenhada, "
            "maximo_adesao) FROM STDIN",
            (
                (
                    carga_id,
                    i.chave,
                    i.ata_id_origem,
                    i.id_item,
                    i.descricao,
                    i.nome_catalogo,
                    i.id_fornecedor,
                    i.fornecedor,
                    i.quantidade,
                    i.valor_unitario,
                    None,
                    i.valor_valido,
                    i.tipo_item,
                    i.codigo_catalogo,
                    i.codigo_pdm,
                    i.nome_pdm,
                    i.quantidade_empenhada,
                    i.maximo_adesao,
                )
                for i in preparado.itens
            ),
        )
        if ativa:
            await conn.execute(
                "UPDATE cargas SET ativa = false, status = 'substituida' WHERE id = %s",
                (ativa["id"],),
            )
            await conn.execute("DELETE FROM atas WHERE carga_id = %s", (ativa["id"],))
        await conn.execute(
            "UPDATE cargas SET ativa = true, status = 'concluida', concluido_em = now(), "
            "contagens = %s WHERE id = %s",
            (json.dumps(contagens), carga_id),
        )
        await conn.execute(
            "INSERT INTO atas_vistas (fonte, id_origem, primeira_vez_vista) "
            "SELECT %s, id_origem, (now() AT TIME ZONE 'America/Sao_Paulo')::date "
            "FROM atas WHERE carga_id = %s ON CONFLICT DO NOTHING",
            (FONTE, carga_id),
        )
    return ResultadoCarga(carga_id, "concluida", contagens)


Anteriores = Mapping[str, tuple[str, list[ItemArp]]]  # id -> (dataHoraAtualizacao, itens)


def dia_de_renovar(ata_id: str, hoje: date) -> bool:
    """Cada ata cai num dia da semana fixo: seus itens são rebuscados ao menos 1x por semana."""
    return int(hashlib.sha256(ata_id.encode()).hexdigest()[:8], 16) % 7 == hoje.toordinal() % 7


async def carregar_anteriores(
    conn: psycopg.AsyncConnection,
) -> dict[str, tuple[str, list[ItemArp]]]:
    """Itens da carga ativa, por ata, para reaproveitar o que não mudou (ADR 0020)."""
    cur = await conn.execute(
        "SELECT a.id_origem, a.atualizado_origem, i.chave, i.id_item, i.descricao, "
        "i.nome_catalogo, i.tipo_item, i.codigo_catalogo, i.codigo_pdm, i.nome_pdm, "
        "i.id_fornecedor, i.fornecedor, i.quantidade, i.valor_unitario, i.valor_valido, "
        "i.quantidade_empenhada, i.maximo_adesao "
        "FROM cargas c JOIN atas a ON a.carga_id = c.id "
        "JOIN ata_itens i ON i.carga_id = a.carga_id AND i.ata_id_origem = a.id_origem "
        "WHERE c.fonte = %s AND c.ativa",
        (FONTE,),
    )
    anteriores: dict[str, tuple[str, list[ItemArp]]] = {}
    for r in await cur.fetchall():
        atualizado, itens = anteriores.setdefault(
            r["id_origem"], (r["atualizado_origem"] or "", [])
        )
        itens.append(
            ItemArp(
                chave=r["chave"],
                ata_id_origem=r["id_origem"],
                id_item=r["id_item"],
                descricao=r["descricao"],
                nome_catalogo=r["nome_catalogo"],
                tipo_item=r["tipo_item"] or "",
                codigo_catalogo=r["codigo_catalogo"],
                codigo_pdm=r["codigo_pdm"],
                nome_pdm=r["nome_pdm"] or "",
                id_fornecedor=r["id_fornecedor"],
                fornecedor=r["fornecedor"] or "",
                quantidade=r["quantidade"],
                valor_unitario=r["valor_unitario"],
                valor_valido=r["valor_valido"],
                quantidade_empenhada=r["quantidade_empenhada"],
                maximo_adesao=r["maximo_adesao"],
            )
        )
    await conn.commit()
    return anteriores


async def _coletar_com(
    client: Any,
    orcamento: _Orcamento,
    hoje: date,
    anteriores: Anteriores,
    cache: CacheItens | None = None,
) -> tuple[Preparado, dict[str, dict[str, object]]]:
    atas, declarado, paginadas = await listar_atas(client, orcamento, hoje)
    log.info("arp_atas_listadas", atas=len(atas), declaradas=declarado, paginadas=paginadas)
    validar_total(atas, declarado)  # falha cedo, antes de gastar a cota com itens
    catalogo = await carregar_catalogo(client, orcamento)
    candidatas = sorted(i for i, a in atas.items() if e_candidata(a.objeto))
    reaproveitar = [
        i
        for i in candidatas
        if i in anteriores
        and anteriores[i][0] == atas[i].atualizado_em
        and not dia_de_renovar(i, hoje)
    ]
    reaproveitadas = set(reaproveitar)
    do_cache = cache.ler() if cache else {}
    pendentes = [i for i in candidatas if i not in reaproveitadas]
    buscar = [i for i in pendentes if i not in do_cache]
    log.info(
        "arp_candidatas",
        candidatas=len(candidatas),
        buscar=len(buscar),
        cache=len(pendentes) - len(buscar),
    )
    itens_por_ata, falhas = await buscar_itens(
        client, orcamento, buscar, cache.gravar if cache else None
    )
    for i in pendentes:
        if i in do_cache and i not in itens_por_ata:
            itens_por_ata[i] = do_cache[i]
    for i in reaproveitar:
        itens_por_ata[i] = anteriores[i][1]
    # Busca falhou numa ata que já tinha itens: manter os anteriores a apagar preço e motivo.
    recuperadas = [i for i in buscar if i not in itens_por_ata and i in anteriores]
    for i in recuperadas:
        itens_por_ata[i] = anteriores[i][1]
    preparado = preparar(atas, itens_por_ata, candidatas, falhas, declarado, catalogo)
    preparado.contagens.update(
        requisicoes=orcamento.requisicoes,
        janelas_paginadas=paginadas,
        atas_itens_buscados=len(buscar),
        atas_itens_reaproveitados=len(reaproveitar),
        atas_itens_do_cache=len(pendentes) - len(buscar),
        atas_itens_da_carga_anterior_por_falha=len(recuperadas),
    )
    return preparado, _geracao(atas, catalogo, declarado)


async def coletar(
    settings: Settings,
    hoje: date,
    client: Any | None = None,
    anteriores: Anteriores | None = None,
    cache: CacheItens | None = None,
) -> tuple[Preparado, dict[str, dict[str, object]]]:
    """Rede: lista, catálogo e itens. `client` permite injetar um cliente nos testes."""
    orcamento = _Orcamento(settings.arp_requests_per_second, settings.arp_max_requisicoes)
    anteriores = anteriores or {}
    if client is not None:
        return await _coletar_com(client, orcamento, hoje, anteriores, cache)
    async with DadosAbertosClient(
        base_url=URL_BASE, timeout=90.0, max_retries=TENTATIVAS_HTTP
    ) as real:
        return await _coletar_com(real, orcamento, hoje, anteriores, cache)


async def _conectar_com_trava() -> psycopg.AsyncConnection:
    conn = await conectar(get_settings())
    if not await tentar_trava_sessao(conn, CHAVE_TRAVA):
        await conn.close()
        raise ErroValidacao("concorrente", "outra execução do Compras ARP já está em andamento")
    return conn


async def principal(validar: bool) -> int:
    conn: psycopg.AsyncConnection | None = None
    carga_id = uuid4()
    geracao: dict[str, dict[str, object]] = {}
    inicio = time.monotonic()
    try:
        settings = get_settings()
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        conn = await (conectar(settings) if validar else _conectar_com_trava())
        try:
            anteriores = await carregar_anteriores(conn)
            cache = CacheItens.do_dia(hoje)
            preparado, geracao = await coletar(settings, hoje, anteriores=anteriores, cache=cache)
            if validar:
                log.info(
                    "arp_validado", segundos=round(time.monotonic() - inicio), **preparado.contagens
                )
                return 0
            resultado = await _publicar(conn, preparado, geracao, carga_id, hoje)
            cache.limpar_antigos()
        except Exception as exc:
            if not validar:
                await _registrar_falha(conn, carga_id, exc, geracao, FONTE)
            raise
        log.info(
            "arp_carga",
            carga_id=str(resultado.carga_id),
            status=resultado.status,
            segundos=round(time.monotonic() - inicio),
            **resultado.contagens,
        )
        return 0
    except ErroValidacao as exc:
        log.error("arp_falha", tipo=exc.tipo, mensagem=str(exc))
        return 1
    except Exception as exc:
        # Sem traceback: exceção do driver pode carregar linhas dos dados.
        log.error("arp_falha", tipo=type(exc).__name__, sqlstate=getattr(exc, "sqlstate", None))
        return 1
    finally:
        if conn is not None:
            await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga das atas vigentes do Compras.gov.br (ARP).")
    parser.add_argument("--validar", action="store_true", help="coleta e valida sem gravar")
    raise SystemExit(asyncio.run(principal(parser.parse_args().validar)))


if __name__ == "__main__":
    main()
