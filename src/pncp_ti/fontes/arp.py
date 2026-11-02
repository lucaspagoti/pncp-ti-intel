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
import os
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Container, Coroutine, Iterable, Mapping, Sequence
from dataclasses import asdict, astuple, dataclass, field, replace
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

from pncp_ti.busca import atualizar_busca
from pncp_ti.classificar.in05 import versao_regra
from pncp_ti.classificar.regra import CATMAT_GRUPO_TI, CATSER_CLASSES_TI
from pncp_ti.config import Settings, get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes import unidades as unidades_pncp
from pncp_ti.fontes.arp_dados import (
    CAMPOS_ATA,
    CAMPOS_ITEM,
    AtaArp,
    CatalogoTI,
    ItemArp,
    chave_sem_id,
    decidir_ata,
    e_candidata,
    escolher,
    itens_ti_por_catalogo,
    mapear_ata,
    mapear_item,
    texto,
    validar_contrato,
    validar_pagina,
)
from pncp_ti.fontes.arp_regra import REGRA_PADRAO, RegraArp
from pncp_ti.fontes.siga import _copiar, _registrar_falha, tentar_trava_sessao
from pncp_ti.fontes.siga_csv import ErroValidacao
from pncp_ti.ingest.rate_limit import LimitadorTaxa

FONTE = "compras_arp"
CHAVE_TRAVA = "carga:compras_arp"
URL_BASE = "https://dadosabertos.compras.gov.br"
ROTA_ATAS = "/modulo-arp/1.2_consultarARP_FimVigencia"
ROTA_ITENS_ATA = "/modulo-arp/2.1_consultarARPItem_Id"
ROTA_ITENS_LOTE = "/modulo-arp/2_consultarARPItem"
ROTA_PDM = "/modulo-material/3_consultarPdmMaterial"
ROTA_SERVICOS = "/modulo-servico/6_consultarItemServico"

TAMANHO_PAGINA = 500
JANELA_DIAS = 365  # limite da API para dataVigenciaFinalMin/Max
JANELAS = 3
ASSINATURA_MINIMA = date(2000, 1, 1)
ASSINATURA_PASSO_INICIAL = 64  # dias; num dia cheio, a assinatura costuma estar ~1 ano antes
ASSINATURA_PASSO_MAXIMO = 4000
ALVO_PAGINA = 0.9  # fração de uma página que a caminhada adaptativa mira por consulta
CONCORRENCIA = 2
TENTATIVAS_HTTP = 6  # o 429 da API pede ~36 s de espera; o cliente respeita o Retry-After
# Na varredura, um par que não responde volta na noite seguinte: em 17/10/2026 um único par deu
# 7 timeouts de 90 s e gastou 36 dos 45 min do orçamento. Duas novas tentativas bastam.
TENTATIVAS_VARREDURA = 2
PISO_ATAS = 0.5
PISO_ITENS = 0.7
ID_PNCP_ATA = re.compile(r"\d{14}-\d-\d{6}/\d{4}-\d{6}")  # CNPJ-1-compra/ano-ata
SEQUENCIAL_ATA = re.compile(r"-\d{6}$")
TOLERANCIA_TOTAL = 0.01  # |linhas explicadas − totalRegistros| em relação ao declarado
LIMITE_SEM_ID = 0.05  # atas sem numeroControlePncpAta (1,7% em 14/10/2026)
LIMITE_CONFLITO_ID = 0.01  # mesmo id com número de ata diferente
LIMITE_SEM_ITEM = 0.05  # candidatas sem item (inclui falhas de busca)

ANOS_VARREDURA_MAXIMO = 5
FORMATO_VARREDURA = 3
FORMATO_CACHE = 2  # muda quando o mapeamento do item ou a regra de completude mudam
# Erros que se repetem iguais numa nova tentativa: dado ou contrato da API, não rede.
ERROS_DETERMINISTICOS = frozenset(
    {
        "total_registros",
        "sem_id_excessivo",
        "conflito_id",
        "contrato",
        "envelope",
        "data_anomala",
        "catalogo",
        "queda_volume",
        "geracao_antiga",
    }
)
SAIDA_DETERMINISTICA = 2

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


@dataclass(slots=True)
class Listagem:
    """Resultado da listagem, com a conta de cada linha que a API declarou (ADR 0021)."""

    atas: dict[str, AtaArp] = field(default_factory=dict)
    # Atas sem `numeroControlePncpAta`: chave natural -> ata com id provisório.
    sem_id: dict[tuple[str, ...], AtaArp] = field(default_factory=dict)
    sem_id_sem_chave: int = 0  # sem id e sem os campos para recuperá-lo
    descartadas: int = 0  # sem fim ou com início inválido
    repetidas: int = 0  # linhas com id já visto (desempate em `escolher`)
    conflitos: int = 0  # mesmo id, número de ata diferente: erro da origem
    exclusao_recente_ignorada: int = 0  # a linha excluída era a mais nova (ADR 0021)
    declarado: int = 0
    paginadas: int = 0
    requisicoes: int = 0

    @property
    def explicadas(self) -> int:
        return len(self.atas) + len(self.sem_id) + self.sem_id_sem_chave + self.descartadas

    def contagens(self) -> dict[str, int]:
        return {
            "atas_declaradas": self.declarado,
            "atas_sem_controle_pncp": len(self.sem_id) + self.sem_id_sem_chave,
            "atas_descartadas": self.descartadas,
            "atas_id_repetido": self.repetidas,
            "atas_conflito_id": self.conflitos,
            "atas_exclusao_recente_ignorada": self.exclusao_recente_ignorada,
            "janelas_paginadas": self.paginadas,
            "requisicoes_listagem": self.requisicoes,
        }


async def _pagina(
    client: DadosAbertosClient, orcamento: _Orcamento, rota: str, pagina: int, **filtros: Any
) -> dict[str, Any]:
    await orcamento.pedir()
    return await client.list_resource(rota, pagina=pagina, tamanho_pagina=TAMANHO_PAGINA, **filtros)


async def listar_atas(client: DadosAbertosClient, orcamento: _Orcamento, hoje: date) -> Listagem:
    """Todas as atas com fim de vigência de hoje em diante, sem depender da paginação.

    A API pagina por offset sem desempate estável: numa janela de duas semanas, 682 de 6.979
    registros vieram repetidos e outros 682 nunca vieram (13/10/2026). Por isso cada consulta
    precisa caber numa página. A caminhada é adaptativa: anda pelo fim da vigência com uma
    janela dimensionada pela densidade da anterior (cerca de 90% de uma página); num dia cheio,
    anda pela data de assinatura, de hoje para trás, até somar o total do dia. Só se nem isso
    couber a faixa é paginada (`paginadas`, risco de perda que a conferência do total mede).
    """
    resultado = Listagem()
    semaforo = asyncio.Semaphore(CONCORRENCIA)
    tamanho = TAMANHO_PAGINA  # a página real, aprendida da primeira resposta cheia

    async def consultar(filtros: dict[str, str], pagina: int = 1):
        nonlocal tamanho
        async with semaforo:
            resposta = await _pagina(client, orcamento, ROTA_ATAS, pagina, **filtros)
        resultado.requisicoes += 1
        registros, total, paginas = validar_pagina(resposta, pagina)
        if pagina == 1 and paginas > 1 and registros:  # a última página vem parcial
            tamanho = len(registros)
        return registros, total, paginas

    def proxima(largura: int, total: int, limite: int) -> int:
        """Dias da próxima janela, mirando ~90% de uma página pela densidade observada."""
        if total == 0:
            return min(limite, largura * 4)
        return max(1, min(limite, largura * int(tamanho * ALVO_PAGINA) // total))

    def cortar(registros: list[dict[str, Any]], campo: str, origem: date, total: int) -> int:
        """Largura que cabe numa página, estimada pela 1ª página de uma janela que estourou.

        A 1ª página é uma amostra do total: a largura que cobre ~90% de uma página em
        proporção da amostra (distância da data de `campo` até a `origem` da caminhada).
        """
        distancias = []
        for bruto in registros:
            try:
                distancias.append(abs((date.fromisoformat(str(bruto[campo])[:10]) - origem).days))
            except (KeyError, ValueError):
                continue
        if not distancias:
            return 0
        distancias.sort()
        k = max(1, min(len(distancias), int(len(distancias) * tamanho * ALVO_PAGINA / total)))
        return distancias[k - 1] + 1

    def encolher(largura: int, total: int, corte: int) -> int:
        """Próxima largura depois de estourar: sempre menor que a atual."""
        estimada = corte or proxima(largura, total, largura)
        return max(1, min(largura - 1, estimada))

    def guardar(registros: list[dict[str, Any]]) -> None:
        validar_contrato(registros, CAMPOS_ATA)
        for bruto in registros:
            if not bruto.get("numeroControlePncpAta"):
                provisoria = mapear_ata(bruto, hoje, id_origem="sem-id")
                chave = chave_sem_id(bruto)
                if provisoria is None:
                    resultado.descartadas += 1
                elif chave is None:
                    resultado.sem_id_sem_chave += 1
                else:
                    atual_sem_id = resultado.sem_id.get(chave)
                    resultado.sem_id[chave] = (
                        provisoria if atual_sem_id is None else escolher(atual_sem_id, provisoria)
                    )
                continue
            ata = mapear_ata(bruto, hoje)
            if ata is None:
                resultado.descartadas += 1
                continue
            atual = resultado.atas.get(ata.id_origem)
            if atual is None:
                resultado.atas[ata.id_origem] = ata
                continue
            resultado.repetidas += 1
            if atual.numero != ata.numero:
                resultado.conflitos += 1
                log.warning("arp_conflito_id", ata=ata.id_origem)
            escolhida = escolher(atual, ata)
            outra = ata if escolhida is atual else atual
            if not outra.vigente_na_origem and outra.atualizado_em > escolhida.atualizado_em:
                resultado.exclusao_recente_ignorada += 1
            resultado.atas[ata.id_origem] = escolhida

    async def paginar(
        filtros: dict[str, str], primeira: list[dict[str, Any]], total: int, paginas: int
    ) -> list[dict[str, Any]]:
        """Todas as páginas, sem as linhas idênticas que a paginação instável repete.

        Total ou número de páginas que mudam no meio: a lista mudou durante a leitura, e a
        janela não pode ser dada como completa (erro transitório; a próxima tentativa refaz).
        """
        resultado.paginadas += 1
        log.warning("arp_janela_paginada", paginas=paginas, **filtros)
        linhas = {json.dumps(r, sort_keys=True, default=str): r for r in primeira}
        for pagina in range(2, paginas + 1):
            registros, total_pagina, paginas_pagina = await consultar(filtros, pagina)
            if (total_pagina, paginas_pagina) != (total, paginas):
                raise ErroValidacao(
                    "listagem_inconsistente",
                    f"página {pagina}: {total_pagina}/{paginas_pagina}, antes {total}/{paginas}",
                )
            linhas.update((json.dumps(r, sort_keys=True, default=str), r) for r in registros)
        return list(linhas.values())

    async def dia_cheio(
        dia: dict[str, str], primeira: list[dict[str, Any]], total_dia: int, paginas_dia: int
    ):
        soma = 0
        fatias: list[dict[str, Any]] = []  # só são guardadas se a soma fechar com o dia
        final, dias = hoje, ASSINATURA_PASSO_INICIAL
        while final >= ASSINATURA_MINIMA and soma < total_dia:
            inicio = max(ASSINATURA_MINIMA, final - timedelta(days=dias - 1))
            filtros = {
                **dia,
                "dataAssinaturaInicial": inicio.isoformat(),
                "dataAssinaturaFinal": final.isoformat(),
            }
            registros, total, paginas = await consultar(filtros)
            largura = (final - inicio).days + 1
            if paginas > 1 and largura > 1:
                corte = cortar(registros, "dataAssinatura", final, total)
                dias = encolher(largura, total, corte)
                continue
            if paginas > 1:
                registros = await paginar(filtros, registros, total, paginas)
            fatias.extend(registros)
            soma += total
            final = inicio - timedelta(days=1)
            dias = proxima(largura, total, ASSINATURA_PASSO_MAXIMO)
        if soma == total_dia:
            guardar(fatias)
        else:
            # Ex.: ata sem data de assinatura some do filtro. Pagina o dia inteiro e descarta
            # as fatias, para nenhuma linha ser contada duas vezes.
            guardar(await paginar(dia, primeira, total_dia, paginas_dia))
        resultado.declarado += total_dia

    async def por_fim(inicio: date, fim: date) -> None:
        dias = 1
        while inicio <= fim:
            final = min(inicio + timedelta(days=dias - 1), fim)
            filtros = {
                "dataVigenciaFinalMin": inicio.isoformat(),
                "dataVigenciaFinalMax": final.isoformat(),
            }
            registros, total, paginas = await consultar(filtros)
            largura = (final - inicio).days + 1
            if paginas > 1 and largura > 1:
                dias = encolher(
                    largura, total, cortar(registros, "dataVigenciaFinal", inicio, total)
                )
                continue
            if paginas > 1:
                await dia_cheio(filtros, registros, total, paginas)
            else:
                guardar(registros)
                resultado.declarado += total
            inicio = final + timedelta(days=1)
            dias = proxima(largura, total, JANELA_DIAS)

    # O primeiro ano concentra quase tudo: duas caminhadas em paralelo, mais uma para o resto.
    (primeiro, fim_ano), *resto = janelas(hoje)
    meio = primeiro + (fim_ano - primeiro) // 2
    await asyncio.gather(
        por_fim(primeiro, meio),
        por_fim(meio + timedelta(days=1), fim_ano),
        por_fim(resto[0][0], resto[-1][1]),
    )
    return resultado


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


# Campos que mudam no mesmo registro entre uma página e outra (empenho, saldo, exclusão).
# Fora da identidade: uma atualização no meio da leitura não pode contar como linha nova e
# esconder uma linha omitida pela paginação (revisão 5 do Codex, 14/10/2026).
CAMPOS_MUTAVEIS = frozenset(
    {
        "dataHoraAtualizacao",
        "dataHoraExclusao",
        "itemExcluido",
        "quantidadeEmpenhada",
        "percentualMaiorDesconto",
        "situacaoSicaf",
        "valorUnitario",
        "valorTotal",
        "maximoAdesao",
        "quantidadeHomologadaItem",
        "quantidadeHomologadaVencedor",
    }
)


def _identidade_linha(bruto: Mapping[str, Any]) -> str:
    """Identidade estável da linha: repete quando a paginação repete a linha, mesmo atualizada.

    A API também devolve o mesmo item duas vezes com `dataHoraInclusao` diferente (reinclusão
    duplicada na origem, 14/10/2026): são linhas distintas e contam para o total declarado.
    Fica só em memória (o documento do fornecedor chega sem máscara).
    """
    estavel = {k: v for k, v in bruto.items() if k not in CAMPOS_MUTAVEIS}
    return hashlib.sha256(json.dumps(estavel, sort_keys=True, default=str).encode()).hexdigest()


async def _itens_da_ata(
    client: DadosAbertosClient, orcamento: _Orcamento, ata_id: str
) -> list[ItemArp]:
    itens: dict[str, tuple[str, ItemArp]] = {}  # chave -> (atualização, item mais recente)
    vistos: set[str] = set()
    declarado: tuple[int, int] | None = None
    pagina = 1
    while True:
        resposta = await _pagina(
            client, orcamento, ROTA_ITENS_ATA, pagina, numeroControlePncpAta=ata_id
        )
        registros, total, paginas = validar_pagina(resposta, pagina)
        # Total ou número de páginas que mudam no meio: a lista mudou durante a leitura.
        if declarado is None:
            declarado = (total, paginas)
        elif (total, paginas) != declarado:
            raise ErroValidacao(
                "itens_inconsistentes",
                f"página {pagina}: {total} itens/{paginas} páginas, antes {declarado}",
            )
        validar_contrato(registros, CAMPOS_ITEM)
        for bruto in registros:
            vistos.add(_identidade_linha(bruto))
            item = mapear_item(bruto)
            if item is None or item.ata_id_origem != ata_id:
                continue
            versao = str(bruto.get("dataHoraAtualizacao") or "")
            anterior = itens.get(item.chave)
            if anterior is None or versao >= anterior[0]:
                itens[item.chave] = (versao, item)  # reinclusão duplicada: fica a mais nova
        if pagina >= paginas:
            break
        pagina += 1
    # A paginação da API pode repetir e omitir linhas (ver `listar_atas`): ata incompleta não
    # vira checkpoint nem carga; conta como falha e o chamador usa os itens anteriores.
    if len(vistos) < total:
        raise ErroValidacao("itens_incompletos", f"{len(vistos)} de {total} linhas distintas")
    return [item for _, item in itens.values()]


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

    def ler(self) -> dict[str, tuple[str, list[ItemArp]]]:
        """`{ata: (dataHoraAtualizacao da ata quando os itens foram buscados, itens)}`.

        Linha de outro formato ou sem versão é ignorada: a ata é rebuscada.
        """
        lidos: dict[str, tuple[str, list[ItemArp]]] = {}
        for caminho in (self.anterior, self.caminho):
            if caminho is None or not caminho.is_file():
                continue
            with caminho.open(encoding="utf-8") as arquivo:
                for linha in arquivo:
                    try:
                        registro = json.loads(linha)
                        if registro.get("formato") != FORMATO_CACHE:
                            continue
                        versao = registro["versao"]
                        if not isinstance(versao, str) or not versao:
                            continue
                        itens = [_item_de_json(i) for i in registro["itens"]]
                        ata = str(registro["ata"])
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue  # linha truncada por queda no meio da escrita
                    lidos[ata] = (versao, itens)
        return lidos

    def gravar(self, ata_id: str, versao: str, itens: list[ItemArp]) -> None:
        linha = json.dumps(
            {
                "formato": FORMATO_CACHE,
                "ata": ata_id,
                "versao": versao,
                "itens": [asdict(i) for i in itens],
            },
            default=str,
        )
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

    await _em_grupo(uma(ata_id) for ata_id in ids)
    return resultado, falhas


@dataclass(slots=True)
class Varredura:
    """Itens de TI do catálogo por ata, achados pelo endpoint em lote com `codigoPdm` (R2.1).

    `itens` guarda `(codigoPdm, numeroItem)` distintos: a paginação repete registros. Fica tudo
    que a API devolve (o filtro de vigentes é de quem usa), para o cache não depender de quais
    atas estavam na listagem do dia em que a consulta foi feita.
    """

    itens: dict[str, set[tuple[int, str]]] = field(default_factory=dict)
    nomes: dict[int, str] = field(default_factory=dict)
    falhas: int = 0
    incompletas: int = 0  # janela de 1 dia ainda paginada: a API perde 1 registro por fronteira
    pendentes: int = 0  # pares que o orçamento de tempo deixou para a próxima noite
    completa: bool = False  # todos os pares do ciclo foram consultados com sucesso

    def adicionar(self, ata: str, pdm: int, numero: str) -> None:
        self.itens.setdefault(ata, set()).add((pdm, numero))

    def pdms(self, ata: str) -> set[int]:
        return {pdm for pdm, _ in self.itens.get(ata, ())}


Janela = tuple[int, date, date]  # (índice, início mínimo, início máximo)
Achados = list[tuple[str, str]]  # (numeroControlePncpAta, numeroItem)


class _PrazoEsgotado(Exception):
    pass


def janelas_do_ciclo(ancora: date, quantidade: int) -> list[Janela]:
    """Janelas de 365 dias fixas a partir do dia em que o ciclo começou.

    Datas fixas fazem o progresso valer entre as noites (e entre semanas). A de índice 0 termina
    seis dias depois da âncora; as seguintes voltam no tempo sem sobrepor.
    """
    resultado = []
    for k in range(quantidade):
        fim = ancora + timedelta(days=6 - JANELA_DIAS * k)
        resultado.append((k, fim - timedelta(days=JANELA_DIAS - 1), fim))
    return resultado


def quantidade_de_janelas(ancora: date, primeiro_inicio: date | None) -> int:
    """Janelas necessárias para chegar ao início mais antigo das vigentes (teto de 5 anos)."""
    if primeiro_inicio is None:
        return 1
    alvo = max(primeiro_inicio, ancora - timedelta(days=365 * ANOS_VARREDURA_MAXIMO))
    dias = (ancora + timedelta(days=6) - alvo).days
    return max(1, -(-(dias + 1) // JANELA_DIAS))


async def _consultar(
    client: Any,
    orcamento: _Orcamento,
    pdm: int,
    minimo: date,
    maximo: date,
    prazo: float | None,
) -> tuple[Achados, str, bool]:
    """Todos os itens de um PDM na janela; parte a janela ao meio se a resposta pagina.

    A paginação da API repete um registro por fronteira de página (ADR 0021): janela que cabe
    numa página não perde nada. Se uma janela de 1 dia ainda pagina, devolve `incompleto`.
    O prazo vale a cada requisição: um par grande não passa do orçamento de tempo.
    """

    def conferir_prazo() -> None:
        if prazo is not None and time.monotonic() >= prazo:
            raise _PrazoEsgotado

    filtros = {
        "codigoPdm": pdm,
        "dataVigenciaInicialMin": minimo.isoformat(),
        "dataVigenciaInicialMax": maximo.isoformat(),
    }
    conferir_prazo()
    resposta = await _pagina(
        client, orcamento, ROTA_ITENS_LOTE, 1, max_retries=TENTATIVAS_VARREDURA, **filtros
    )
    registros, _, paginas = validar_pagina(resposta, 1)
    if paginas > 1 and minimo < maximo:
        meio = minimo + (maximo - minimo) // 2
        a, nome_a, inc_a = await _consultar(client, orcamento, pdm, minimo, meio, prazo)
        b, nome_b, inc_b = await _consultar(
            client, orcamento, pdm, meio + timedelta(days=1), maximo, prazo
        )
        return a + b, nome_a or nome_b, inc_a or inc_b
    achados: Achados = []
    nome = ""
    pagina = 1
    while True:
        for r in registros:
            ata, numero = r.get("numeroControlePncpAta"), r.get("numeroItem")
            if ata and numero is not None and r.get("itemExcluido") is not True:
                achados.append((str(ata), str(numero)))
                nome = nome or str(r.get("nomePdm") or "")
        if pagina >= paginas:
            return achados, nome, paginas > 1
        pagina += 1
        conferir_prazo()
        resposta = await _pagina(
            client, orcamento, ROTA_ITENS_LOTE, pagina, max_retries=TENTATIVAS_VARREDURA, **filtros
        )
        registros, _, paginas = validar_pagina(resposta, pagina)


async def varrer_pdm(
    client: Any,
    orcamento: _Orcamento,
    pdms: Iterable[int],
    janelas: Sequence[Janela],
    feitos: Container[tuple[int, int]] = frozenset(),
    ao_concluir: Callable[[int, int, Achados, str, bool], None] | None = None,
    prazo: float | None = None,
) -> Varredura:
    """Uma consulta por (PDM de TI, janela de início de vigência); pula os pares já feitos.

    Falha de uma consulta conta em `falhas`, não derruba a carga e deixa o par para a próxima
    execução (a varredura só acrescenta candidatas). O teto de requisições, esse sim, sobe.
    `prazo` (instante de `time.monotonic()`) interrompe também no meio de um par, mas só depois
    da primeira tentativa da execução: o par interrompido não é gravado e, com os
    seguintes, vira `pendentes`.
    """
    varredura = Varredura()
    parado = False
    tentou = False
    for pdm in pdms:  # a ordem é de quem chama: os PDMs centrais primeiro rendem mais cedo
        for k, minimo, maximo in janelas:
            if (pdm, k) in feitos:
                continue
            if parado:
                varredura.pendentes += 1
                continue
            try:
                # A 1ª tentativa da execução ignora o prazo: todo ciclo avança ao menos um par por
                # noite, mesmo que um par sozinho leve mais que o orçamento. Só a 1ª: se ela falha
                # (API fora), as seguintes já respeitam o prazo.
                primeira, tentou = not tentou, True
                achados, nome, incompleto = await _consultar(
                    client, orcamento, pdm, minimo, maximo, None if primeira else prazo
                )
            except _PrazoEsgotado:
                parado = True
                varredura.pendentes += 1
                continue
            except ErroValidacao as exc:
                if exc.tipo == "teto_requisicoes":
                    raise
                varredura.falhas += 1
                log.warning("arp_varredura_falha", pdm=pdm, erro=exc.tipo)
                continue
            except ComprasError as exc:
                varredura.falhas += 1
                log.warning("arp_varredura_falha", pdm=pdm, erro=type(exc).__name__)
                continue
            varredura.incompletas += incompleto
            for ata, numero in achados:
                varredura.adicionar(ata, pdm, numero)
            if nome:
                varredura.nomes[pdm] = nome
            if ao_concluir:
                ao_concluir(pdm, k, achados, nome, incompleto)
    return varredura


_CICLO = re.compile(r"varredura-(\d{4}-\d{2}-\d{2})\.jsonl")
CICLO_DIAS = 7  # um ciclo completo só recomeça passada uma semana


class CacheVarredura:
    """Progresso do ciclo de varredura em disco (uma linha JSON por par PDM x janela).

    A varredura de todos os PDMs é a parte lenta (a API chega a 10-30 s por consulta): o
    progresso fica guardado e a próxima noite continua de onde parou, mesmo se atravessar a
    semana. Um ciclo só recomeça depois de completo e com mais de `CICLO_DIAS` dias. Trocar a
    versão do catálogo recomeça. A primeira linha é o cabeçalho; `{"completa": true}` fecha.
    Os arquivos são criados sem seguir links e com modo 0600.
    """

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho

    @classmethod
    def do_ciclo(cls, hoje: date, raiz: Path = RAIZ_CACHE) -> CacheVarredura:
        raiz.mkdir(parents=True, exist_ok=True, mode=0o700)
        if raiz.stat().st_uid == os.getuid():
            raiz.chmod(0o700)
        ciclos = sorted(
            (m.group(1), p)
            for p in raiz.glob("varredura-*.jsonl")
            if (m := _CICLO.fullmatch(p.name))
        )
        if ciclos:
            data, ultimo = ciclos[-1]
            completo = _terminou(ultimo)
            if not completo or (hoje - date.fromisoformat(data)).days < CICLO_DIAS:
                return cls(ultimo)
        return cls(raiz / f"varredura-{hoje.isoformat()}.jsonl")

    def ler(
        self, versao_catalogo: str
    ) -> tuple[date, int, set[tuple[int, int]], Varredura, bool] | None:
        """`(âncora, janelas, feitos, progresso, completa)`, ou `None` sem progresso válido."""
        try:
            linhas = self.caminho.read_text(encoding="utf-8").splitlines()
            cabecalho = json.loads(linhas[0])
            if (
                cabecalho["formato"] != FORMATO_VARREDURA
                or cabecalho["catalogo"] != versao_catalogo
            ):
                return None
            feitos: set[tuple[int, int]] = set()
            progresso = Varredura()
            completa = False
            for linha in linhas[1:]:
                try:
                    registro = json.loads(linha)
                except ValueError:
                    continue  # linha truncada por queda no meio da escrita: o par se repete
                if registro.get("completa") is True:
                    completa = True
                    continue
                pdm, k = int(registro["pdm"]), int(registro["k"])
                feitos.add((pdm, k))
                progresso.incompletas += bool(registro.get("inc"))
                if registro.get("nome"):
                    progresso.nomes[pdm] = str(registro["nome"])
                for ata, numero in registro["itens"]:
                    progresso.adicionar(str(ata), pdm, str(numero))
            ancora = date.fromisoformat(cabecalho["ancora"])
            return ancora, int(cabecalho["janelas"]), feitos, progresso, completa
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            return None

    def _anexar(self, texto: str, *, recomecar: bool = False) -> None:
        flags = (
            os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_TRUNC if recomecar else os.O_APPEND)
        )
        descritor = os.open(self.caminho, flags, 0o600)
        with os.fdopen(descritor, "a" if not recomecar else "w", encoding="utf-8") as arquivo:
            # Cauda truncada por queda de energia: fecha a linha antes de acrescentar a nova.
            if not recomecar and arquivo.tell() and not _termina_em_quebra(self.caminho):
                arquivo.write("\n")
            arquivo.write(texto + "\n")

    def iniciar(self, versao_catalogo: str, ancora: date, janelas: int) -> None:
        cabecalho = {
            "formato": FORMATO_VARREDURA,
            "catalogo": versao_catalogo,
            "ancora": ancora.isoformat(),
            "janelas": janelas,
        }
        self._anexar(json.dumps(cabecalho), recomecar=True)

    def gravar_par(self, pdm: int, k: int, achados: Achados, nome: str, incompleto: bool) -> None:
        registro = {"pdm": pdm, "k": k, "nome": nome, "inc": incompleto, "itens": achados}
        self._anexar(json.dumps(registro))

    def marcar_completa(self) -> None:
        self._anexar(json.dumps({"completa": True}))

    def limpar_antigos(self) -> None:
        for antigo in self.caminho.parent.glob("varredura-*.json*"):
            if antigo != self.caminho:
                antigo.unlink(missing_ok=True)


def _termina_em_quebra(caminho: Path) -> bool:
    with caminho.open("rb") as arquivo:
        arquivo.seek(-1, os.SEEK_END)
        return arquivo.read(1) == b"\n"


def _terminou(caminho: Path) -> bool:
    try:
        ultima = [linha for linha in caminho.read_text(encoding="utf-8").splitlines() if linha][-1]
        return json.loads(ultima).get("completa") is True
    except (OSError, ValueError, IndexError, AttributeError):
        return False


async def obter_varredura(
    client: Any,
    orcamento: _Orcamento,
    catalogo: CatalogoTI,
    atas: Mapping[str, AtaArp],
    hoje: date,
    cache: CacheVarredura | None,
    minutos: float | None = None,
    regra: RegraArp = REGRA_PADRAO,
) -> Varredura:
    """Varredura por PDM retomável: continua o ciclo em andamento e respeita o prazo da noite."""
    inicios = [a.inicio for a in atas.values() if a.inicio]
    versao = catalogo.versao()
    estado = cache.ler(versao) if cache else None
    if estado is None:
        ancora = hoje
        janelas = quantidade_de_janelas(ancora, min(inicios) if inicios else None)
        feitos: set[tuple[int, int]] = set()
        resultado = Varredura()
        if cache:
            try:
                cache.iniciar(versao, ancora, janelas)
            except OSError as exc:  # sem cache o ciclo vale só para esta noite
                log.warning("arp_varredura_cache_indisponivel", erro=type(exc).__name__)
                cache = None
    else:
        ancora, janelas, feitos, resultado, completa = estado
        esperados = {(p, k) for p in catalogo.pdms for k in range(janelas)}
        if completa and esperados <= feitos:
            resultado.completa = True
            return resultado
    prazo = time.monotonic() + minutos * 60 if minutos else None
    # Centrais primeiro: com a API lenta o ciclo leva várias noites, e eles valem mais.
    ordem = sorted(catalogo.pdms, key=lambda p: (p not in regra.pdms_centrais, p))
    nova = await varrer_pdm(
        client,
        orcamento,
        ordem,
        janelas_do_ciclo(ancora, janelas),
        feitos,
        cache.gravar_par if cache else None,
        prazo,
    )
    for ata, itens in nova.itens.items():
        resultado.itens.setdefault(ata, set()).update(itens)
    resultado.nomes.update(nova.nomes)
    resultado.falhas = nova.falhas
    resultado.incompletas += nova.incompletas
    resultado.pendentes = nova.pendentes
    resultado.completa = nova.falhas == 0 and nova.pendentes == 0
    if cache and resultado.completa:
        cache.marcar_completa()
    return resultado


def candidatas_da_varredura(varredura: Varredura, atas: Mapping[str, AtaArp]) -> set[str]:
    """Toda ata vigente com ao menos um item de TI do catálogo achado pela varredura.

    Não há pré-corte: a contagem de itens da listagem pode divergir dos itens reais, então o
    corte exato (`decidir_ata`) roda sobre os itens buscados. As incidentais custam a busca
    de itens uma vez; depois os itens são reaproveitados da carga anterior.
    """
    return {ata for ata in varredura.itens if ata in atas}


def validar_total(listagem: Listagem) -> None:
    """Toda linha declarada pela API tem de estar explicada: ata, sem id ou descartada.

    O que sobra é perda (paginação, linha repetida no lugar de outra) e tolera até 1%.
    """
    declarado = listagem.declarado
    if not listagem.atas:
        raise ErroValidacao("sem_atas", "a API não devolveu nenhuma ata vigente")
    sem_id = len(listagem.sem_id) + listagem.sem_id_sem_chave
    if sem_id > LIMITE_SEM_ID * declarado:
        raise ErroValidacao("sem_id_excessivo", f"{sem_id} de {declarado} atas sem id do PNCP")
    if listagem.conflitos > LIMITE_CONFLITO_ID * declarado:
        raise ErroValidacao("conflito_id", f"{listagem.conflitos} ids com atas diferentes")
    if declarado and abs(listagem.explicadas - declarado) > TOLERANCIA_TOTAL * declarado:
        raise ErroValidacao(
            "total_registros",
            f"{listagem.explicadas} linhas explicadas ({len(listagem.atas)} atas únicas) "
            f"contra {declarado} declaradas",
        )


async def _em_grupo(tarefas: Iterable[Coroutine[Any, Any, None]]) -> None:
    """Roda as tarefas num `TaskGroup` e relança o erro de validação sem o `ExceptionGroup`.

    Assim `teto_requisicoes` chega a `principal` com o tipo certo (log e código de saída).
    """
    try:
        async with asyncio.TaskGroup() as grupo:
            for tarefa in tarefas:
                grupo.create_task(tarefa)
    except* ErroValidacao as erros:
        raise erros.exceptions[0] from None


async def recuperar_ids(
    client: DadosAbertosClient, orcamento: _Orcamento, listagem: Listagem
) -> tuple[dict[str, AtaArp], int]:
    """Id do PNCP das candidatas sem `numeroControlePncpAta`, pelo endpoint de itens em lote.

    A listagem de atas omite o id de cerca de 1,7% delas, mas os itens trazem (14/10/2026).
    Uma consulta por (unidade, compra, início) mapeia o número da ata para o id. A linha do
    lote só conta se unidade, compra, início (e ano, se vier) baterem com o grupo; o id só vale
    se tiver o formato do PNCP, começar pelo id da compra da ata (quando a listagem o traz),
    for único para o número e não existir na listagem nem em outra recuperação. Falha numa
    consulta não derruba a carga: a ata fica sem id e contada. Devolve `(recuperadas, falhas)`.
    """
    grupos: dict[tuple[str, ...], dict[str, AtaArp]] = defaultdict(dict)
    for (unidade, compra, ano, inicio, numero), ata in listagem.sem_id.items():
        if e_candidata(ata.objeto):
            grupos[(unidade, compra, ano, inicio)][numero] = ata
    achadas: list[AtaArp] = []
    falhas = 0
    semaforo = asyncio.Semaphore(CONCORRENCIA)

    async def um(grupo: tuple[str, ...], atas: dict[str, AtaArp]) -> None:
        nonlocal falhas
        unidade, compra, ano, inicio = grupo
        filtros = {
            "codigoUnidadeGerenciadora": unidade,
            "numeroCompra": compra,
            "dataVigenciaInicialMin": inicio,
            "dataVigenciaInicialMax": inicio,
        }
        ids: dict[str, set[str]] = defaultdict(set)
        vistos: set[str] = set()
        declarado: tuple[int, int] | None = None
        try:
            pagina = 1
            while True:
                async with semaforo:
                    resposta = await _pagina(client, orcamento, ROTA_ITENS_LOTE, pagina, **filtros)
                registros, total, paginas = validar_pagina(resposta, pagina)
                if declarado is None:
                    declarado = (total, paginas)
                elif (total, paginas) != declarado:
                    raise ErroValidacao("lote_inconsistente", "totais mudaram na paginação")
                for r in registros:
                    vistos.add(_identidade_linha(r))
                    # A API pode ignorar um filtro: a linha tem de ser do grupo.
                    if (
                        texto(r.get("codigoUnidadeGerenciadora")) != unidade
                        or texto(r.get("numeroCompra")) != compra
                        or texto(r.get("dataVigenciaInicial"))[:10] != inicio
                        or texto(r.get("anoCompra")) not in ("", ano)
                    ):
                        continue
                    numero = texto(r.get("numeroAtaRegistroPreco"))
                    id_pncp = texto(r.get("numeroControlePncpAta"))
                    if numero in atas and ID_PNCP_ATA.fullmatch(id_pncp):
                        ids[numero].add(id_pncp)
                if pagina >= paginas:
                    break
                pagina += 1
            # A paginação pode omitir linhas: um 2º id do mesmo número sumiria. Sem todas as
            # linhas, nenhum id do grupo é aceito.
            if declarado is not None and len(vistos) < declarado[0]:
                raise ErroValidacao("lote_incompleto", f"{len(vistos)} de {declarado[0]} linhas")
        except ErroValidacao as exc:
            if exc.tipo == "teto_requisicoes":
                raise
            falhas += 1
            log.warning("arp_recuperar_id_falha", tipo=exc.tipo)
            return
        except ComprasError as exc:
            falhas += 1
            log.warning("arp_recuperar_id_falha", tipo=type(exc).__name__)
            return
        for numero, achados in ids.items():
            if len(achados) != 1:
                continue
            (id_pncp,) = achados
            compra_pncp = atas[numero].numero_controle_pncp_compra
            if compra_pncp and not id_pncp.startswith(f"{compra_pncp}-"):
                continue
            if id_pncp not in listagem.atas:
                achadas.append(replace(atas[numero], id_origem=id_pncp))

    await _em_grupo(um(grupo, atas) for grupo, atas in grupos.items())
    vezes = Counter(a.id_origem for a in achadas)
    # Duas atas sem id que levam ao mesmo id: ambíguo, nenhuma é recuperada.
    return {a.id_origem: a for a in achadas if vezes[a.id_origem] == 1}, falhas


def compra_da_ata(ata: AtaArp) -> str:
    """Compra a que a ata pertence: o ARP emite uma ata por fornecedor (ADR 0025, item 7).

    Sem `numeroControlePncpCompra`, usa o id da ata sem o sequencial (`-NNNNNN`); sem nenhum
    dos dois, a ata é a própria compra.
    """
    return ata.numero_controle_pncp_compra or SEQUENCIAL_ATA.sub("", ata.id_origem)


def contas_por_compra(
    atas: Mapping[str, AtaArp],
    itens_por_ata: Mapping[str, list[ItemArp]],
    catalogo: CatalogoTI,
) -> dict[str, tuple[int, int]]:
    """(itens de TI, itens) de cada compra, somando as atas de todos os fornecedores.

    Conta por `id_item`, que é o número do item na compra: um item dividido entre dois
    fornecedores conta uma vez. A ata cujos itens não foram buscados entra pela
    `quantidade_itens` da listagem; toda ata com item de TI de material já foi buscada
    (é candidata pela varredura), então ela só soma ao total. Serviço de TI (CATSER) não é
    varrido: numa ata não buscada, ele conta como item que não é de TI.
    """
    ti: dict[str, set[str]] = defaultdict(set)
    buscados: dict[str, set[str]] = defaultdict(set)
    da_listagem: dict[str, int] = defaultdict(int)
    for id_origem, ata in atas.items():
        compra = compra_da_ata(ata)
        do_ata = itens_por_ata.get(id_origem)
        if do_ata:
            buscados[compra].update(i.id_item for i in do_ata)
            ti[compra].update(itens_ti_por_catalogo(do_ata, catalogo))
        else:
            da_listagem[compra] += ata.quantidade_itens or 0
    compras = {compra_da_ata(a) for a in atas.values()}
    return {c: (len(ti[c]), len(buscados[c]) + da_listagem[c]) for c in compras}


@dataclass(slots=True)
class Preparado:
    atas: list[AtaArp]
    itens: list[ItemArp]
    decisoes: dict[str, tuple[bool, str]]
    contagens: dict[str, int]
    # Itens de fallback (busca falhou): `atualizado_origem` vai nulo e a próxima carga rebusca.
    versao_itens: dict[str, str | None] = field(default_factory=dict)


def preparar(
    atas: Mapping[str, AtaArp],
    itens_por_ata: Mapping[str, list[ItemArp]],
    candidatas: Sequence[str],
    falhas: int,
    declarado: int,
    catalogo: CatalogoTI,
    regra: RegraArp = REGRA_PADRAO,
) -> Preparado:
    """Valida o conjunto e classifica; sem rede nem banco (o total é conferido na listagem)."""
    if not atas:
        raise ErroValidacao("sem_atas", "a API não devolveu nenhuma ata vigente")
    sem_item = [a for a in candidatas if not itens_por_ata.get(a)]
    if candidatas and len(sem_item) > LIMITE_SEM_ITEM * len(candidatas):
        raise ErroValidacao(
            "itens_ausentes", f"{len(sem_item)} de {len(candidatas)} candidatas sem item"
        )

    itens: dict[str, ItemArp] = {}
    decisoes: dict[str, tuple[bool, str]] = {}
    contas = contas_por_compra(atas, itens_por_ata, catalogo)
    for id_origem, ata in atas.items():
        do_ata = itens_por_ata.get(id_origem, [])
        for item in do_ata:
            itens[item.chave] = item
        decisao = decidir_ata(ata.objeto, do_ata, catalogo, regra, contas[compra_da_ata(ata)])
        decisoes[id_origem] = (decisao.is_ti, decisao.motivo)

    contagens = {
        "atas_unicas": len(atas),
        "atas_declaradas": declarado,
        "atas_candidatas": len(candidatas),
        "candidatas_sem_item": len(sem_item),
        "falhas_busca_itens": falhas,
        "itens_gravados": len(itens),
        "atas_ti": sum(1 for ti, _ in decisoes.values() if ti),
        "atas_incidentais": sum(1 for _, m in decisoes.values() if m == "catalogo_incidental"),
        "atas_vigentes_ti": sum(
            1 for i, a in atas.items() if a.vigente_na_origem and decisoes[i][0]
        ),
    }
    return Preparado(list(atas.values()), list(itens.values()), decisoes, contagens)


def _geracao(
    atas: Mapping[str, AtaArp], catalogo: CatalogoTI, declarado: int, regra: RegraArp = REGRA_PADRAO
) -> dict[str, dict[str, object]]:
    resumo = hashlib.sha256()
    for id_origem in sorted(atas):
        resumo.update(f"{id_origem}\x1f{atas[id_origem].atualizado_em}\x1e".encode())
    return {
        "atas": {"declarado": declarado, "unicas": len(atas), "sha256": resumo.hexdigest()},
        "_regra": {
            "versao": versao_regra(),
            "catalogo": catalogo.versao(),
            "arp": regra.versao(),
        },
    }


async def _publicar(
    conn: psycopg.AsyncConnection,
    preparado: Preparado,
    geracao: dict[str, dict[str, object]],
    carga_id: UUID,
    hoje: date,
    unidades: Mapping[unidades_pncp.Chave, unidades_pncp.Unidade] | None = None,
) -> ResultadoCarga:
    contagens = preparado.contagens
    unidades = unidades or {}

    def local(a: AtaArp) -> unidades_pncp.Unidade:
        c = unidades_pncp.chave(a.id_origem, a.codigo_unidade)
        return unidades.get(c, unidades_pncp.SEM_CADASTRO) if c else unidades_pncp.SEM_CADASTRO

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
            "quantidade_itens, atualizado_origem, esfera, uf, municipio) FROM STDIN",
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
                    preparado.versao_itens.get(a.id_origem, a.atualizado_em) or None,
                    *astuple(local(a)),
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


def codigo_saida(exc: ErroValidacao) -> int:
    """2 para erro que se repetiria igual numa nova tentativa (dado ou contrato); 1 se não."""
    return SAIDA_DETERMINISTICA if exc.tipo in ERROS_DETERMINISTICOS else 1


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
    cache_varredura: CacheVarredura | None = None,
    regra: RegraArp = REGRA_PADRAO,
    minutos_varredura: float | None = None,
) -> tuple[Preparado, dict[str, dict[str, object]]]:
    listagem = await listar_atas(client, orcamento, hoje)
    log.info("arp_atas_listadas", atas=len(listagem.atas), **listagem.contagens())
    validar_total(listagem)  # falha cedo, antes de gastar a cota com itens
    declarado = listagem.declarado
    recuperadas_id, falhas_id = await recuperar_ids(client, orcamento, listagem)
    atas = {**listagem.atas, **recuperadas_id}
    catalogo = await carregar_catalogo(client, orcamento)
    do_objeto = {i for i, a in atas.items() if e_candidata(a.objeto)}
    varredura = await obter_varredura(
        client, orcamento, catalogo, atas, hoje, cache_varredura, minutos_varredura, regra
    )
    da_varredura = candidatas_da_varredura(varredura, atas)
    # Quem já tinha itens na carga anterior continua candidata: varredura parcial não derruba TI.
    candidatas = sorted(do_objeto | da_varredura | {i for i in anteriores if i in atas})
    reaproveitar = [
        i
        for i in candidatas
        if i in anteriores
        # Versão vazia = itens de fallback ou desconhecidos: sempre rebuscar.
        and anteriores[i][0]
        and anteriores[i][0] == atas[i].atualizado_em
        and not dia_de_renovar(i, hoje)
    ]
    reaproveitadas = set(reaproveitar)
    do_cache = {
        i: itens
        for i, (versao, itens) in (cache.ler() if cache else {}).items()
        # Ata mudou desde a busca: rebuscar.
        if i in atas and versao == atas[i].atualizado_em
    }
    pendentes = [i for i in candidatas if i not in reaproveitadas]
    buscar = [i for i in pendentes if i not in do_cache]
    log.info(
        "arp_candidatas",
        candidatas=len(candidatas),
        buscar=len(buscar),
        cache=len(pendentes) - len(buscar),
    )
    gravar = (lambda i, itens: cache.gravar(i, atas[i].atualizado_em, itens)) if cache else None
    itens_por_ata, falhas = await buscar_itens(client, orcamento, buscar, gravar)
    for i in pendentes:
        if i in do_cache and i not in itens_por_ata:
            itens_por_ata[i] = do_cache[i]
    for i in reaproveitar:
        itens_por_ata[i] = anteriores[i][1]
    # Busca falhou numa ata que já tinha itens: manter os anteriores a apagar preço e motivo.
    recuperadas = [i for i in buscar if i not in itens_por_ata and i in anteriores]
    versoes: dict[str, str | None] = {}
    for i in recuperadas:
        itens_por_ata[i] = anteriores[i][1]
        # Versão nula: a próxima carga rebusca, mesmo que a ata não mude (renovação que falhou).
        versoes[i] = None
    preparado = preparar(atas, itens_por_ata, candidatas, falhas, declarado, catalogo, regra)
    preparado.versao_itens = versoes
    preparado.contagens.update(
        listagem.contagens(),
        atas_sem_id_candidatas=sum(1 for a in listagem.sem_id.values() if e_candidata(a.objeto)),
        atas_id_recuperado=len(recuperadas_id),
        falhas_recuperacao_id=falhas_id,
        requisicoes=orcamento.requisicoes,
        atas_itens_buscados=len(buscar),
        atas_itens_reaproveitados=len(reaproveitar),
        atas_itens_do_cache=len(pendentes) - len(buscar),
        atas_itens_da_carga_anterior_por_falha=len(recuperadas),
        varredura_atas=len(varredura.itens),
        varredura_candidatas_novas=len(da_varredura - do_objeto),
        varredura_falhas=varredura.falhas,
        varredura_pendentes=varredura.pendentes,
        varredura_incompletas=varredura.incompletas,
        varredura_completa=int(varredura.completa),
    )
    return preparado, _geracao(atas, catalogo, declarado, regra)


async def coletar(
    settings: Settings,
    hoje: date,
    client: Any | None = None,
    anteriores: Anteriores | None = None,
    cache: CacheItens | None = None,
    cache_varredura: CacheVarredura | None = None,
    regra: RegraArp = REGRA_PADRAO,
) -> tuple[Preparado, dict[str, dict[str, object]]]:
    """Rede: lista, catálogo, varredura por PDM e itens (`client` injeta um cliente nos testes)."""
    orcamento = _Orcamento(settings.arp_requests_per_second, settings.arp_max_requisicoes)
    anteriores = anteriores or {}
    if client is not None:
        return await _coletar_com(
            client,
            orcamento,
            hoje,
            anteriores,
            cache,
            cache_varredura,
            regra,
            settings.arp_varredura_minutos,
        )
    async with DadosAbertosClient(
        base_url=URL_BASE, timeout=90.0, max_retries=TENTATIVAS_HTTP
    ) as real:
        return await _coletar_com(
            real,
            orcamento,
            hoje,
            anteriores,
            cache,
            cache_varredura,
            regra,
            settings.arp_varredura_minutos,
        )


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
            cache_varredura = CacheVarredura.do_ciclo(hoje)
            preparado, geracao = await coletar(
                settings, hoje, anteriores=anteriores, cache=cache, cache_varredura=cache_varredura
            )
            if validar:
                log.info(
                    "arp_validado", segundos=round(time.monotonic() - inicio), **preparado.contagens
                )
                return 0
            chaves = (unidades_pncp.chave(a.id_origem, a.codigo_unidade) for a in preparado.atas)
            unidades, contagens_unidades = await unidades_pncp.resolver(conn, filter(None, chaves))
            preparado.contagens.update(contagens_unidades)
            resultado = await _publicar(conn, preparado, geracao, carga_id, hoje, unidades)
            cache.limpar_antigos()
            cache_varredura.limpar_antigos()
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
        return 0 if await atualizar_busca(conn) else 1
    except ErroValidacao as exc:
        log.error("arp_falha", tipo=exc.tipo, mensagem=str(exc))
        # 2: repetir agora daria o mesmo erro (supervisor e timer não insistem).
        return codigo_saida(exc)
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
