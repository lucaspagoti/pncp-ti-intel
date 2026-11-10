"""Atas vigentes de TI pela API oficial de consultas do PNCP (R3.1, ADR 0038).

Substitui a busca do portal (`pncp_busca`, ADR 0023) como coletor diário da mesma fonte: a
carga continua sendo `fonte = 'pncp_busca'`, com as mesmas colunas e `motivo_ti =
termo_pncp:<termos>`, e as views não mudam. O portal de busca derruba ~60–76% das conexões de
script (ADR 0037); a API de consultas é documentada e responde, com 429 só em rajada.

- **Delta** (padrão, na carga diária): `/v1/atas/atualizacao` desde a marca d'água da última
  carga deste coletor (com um dia de sobreposição) até hoje, aplicado sobre a carga ativa:
  entra ou atualiza a ata vigente, não cancelada, cujo objeto casa algum termo de
  `insumos/termos_ti.txt`; sai a cancelada, a vencida ou a que deixou de casar. São ~2 mil
  atas por dia (~5 páginas de 500). Sem marca d'água, lê os últimos `DIAS_SEM_MARCA` dias.
- **Semente** (`--semente`, unit mensal própria, fora da carga diária): `/v1/atas` com
  vigência de hoje até um ano (~480 mil atas, ~970 páginas, ~7 h no ritmo do portal),
  filtrada localmente pelos termos. É aditiva como o delta: só tira da base a ata que a API
  mostra cancelada, vencida ou sem termo, porque a lista muda durante as horas de leitura e
  uma ata pulada pela paginação não pode sumir. Guarda cada página num checkpoint e retoma
  de onde parou; não segura a trava da fonte enquanto lê, para não bloquear a carga diária.

O filtro é o mesmo `casa_termo` da busca, só que sem a janela de 10 mil resultados por termo.

    python -m pncp_ti.fontes.pncp_atas             # delta
    python -m pncp_ti.fontes.pncp_atas --semente   # varredura completa, com retomada
    python -m pncp_ti.fontes.pncp_atas --validar   # coleta o delta e compara, sem gravar
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import structlog
from compras_mcp.clients.pncp import PNCPClient
from compras_mcp.errors import (
    ComprasError,
    ComprasHTTPError,
    ComprasRateLimitError,
    ComprasServerError,
    ComprasTimeoutError,
)

from pncp_ti.busca import atualizar_busca
from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes import pncp_busca as busca
from pncp_ti.fontes import unidades as unidades_pncp
from pncp_ti.fontes.pncp_busca import (
    ID_PNCP_ATA,
    URL_PORTAL,
    AtaBusca,
    Coleta,
    Telemetria,
    _sem_acento,
    _texto,
)
from pncp_ti.fontes.siga import _registrar_falha, tentar_trava_sessao
from pncp_ti.fontes.siga_csv import ErroValidacao
from pncp_ti.ingest.rate_limit import LimitadorTaxa

FONTE = busca.FONTE  # mesma fonte, mesmas views (ADR 0038)
COLETOR = "api_consulta"
URL_CONSULTA = "https://pncp.gov.br/api/consulta"
ROTA_DELTA = "/v1/atas/atualizacao"
ROTA_VIGENCIA = "/v1/atas"
TAMANHO_PAGINA = 500  # o OpenAPI e o teste real aceitam 500 nas rotas de atas
REQUISICOES_POR_SEGUNDO = 0.4  # 429 apareceu com ~1 req/s em rajada; 1 a cada 2,5 s passou
TENTATIVAS = 6
ESPERA_BASE = 5.0
ESPERA_MAXIMA = 120.0
TIMEOUT = 90.0
SOBREPOSICAO_DIAS = 1  # o delta relê o último dia: atualização tardia não se perde
DIAS_SEM_MARCA = 7  # primeira carga do coletor: delta da última semana sobre a carga ativa
DIAS_MAXIMOS_DELTA = 30  # marca d'água mais velha: lê só 30 dias e avisa (a semente corrige)
VIGENCIA_DIAS = 364  # a API recusa período maior que 365 dias; pega a ata que começa depois
PROGRESSO_A_CADA = 50  # páginas
RETOMADAS = 3  # a semente espera e retoma da página que falhou
ESPERA_RETOMADA = 600.0
DIAS_CHECKPOINT = 3  # checkpoint mais velho que isso é descartado
ESPERA_TRAVA = 60.0  # a semente espera a carga diária soltar a trava da fonte
TENTATIVAS_TRAVA = 90
ARQUIVO_CHECKPOINT = (
    Path(os.environ.get("PNCP_TI_ESTADO", Path.home() / ".local/state/pncp-ti"))
    / "semente_pncp_atas.jsonl"
)
CAMPOS_ITEM = (
    "numeroControlePNCPAta",
    "objetoContratacao",
    "vigenciaFim",
    "cancelado",
    "dataAtualizacaoGlobal",
)
CAMPOS_GUARDADOS = (
    *CAMPOS_ITEM,
    "vigenciaInicio",
    "nomeOrgao",
    "nomeUnidadeOrgao",
    "codigoUnidadeOrgao",
    "numeroAtaRegistroPreco",
    "anoAta",
)
STATUS_ORIGEM = "Divulgada no PNCP"
ID_LINK = re.compile(r"(\d{14})-\d-(\d{6})/(\d{4})-(\d{6})")

log = structlog.get_logger()


@dataclass(slots=True)
class Delta:
    """O que a API trouxe, já mapeado: atas que entram e ids que saem."""

    entram: dict[str, AtaBusca] = field(default_factory=dict)
    saem: set[str] = field(default_factory=set)
    unidades: dict[str, str] = field(default_factory=dict)  # id da ata -> código da unidade
    versoes: dict[str, str] = field(default_factory=dict)  # id da ata -> data de atualização
    lidos: int = 0
    descartados: int = 0  # sem id válido, sem objeto ou sem vigência


def padroes(termos: Sequence[str]) -> dict[str, re.Pattern[str]]:
    return {t: p for t in termos if (p := busca.padrao_termo(t)) is not None}


def termos_que_casam(objeto: str, pads: Mapping[str, re.Pattern[str]]) -> set[str]:
    texto = _sem_acento(objeto)
    return {t for t, p in pads.items() if p.search(texto)}


def link(id_ata: str) -> str | None:
    """`00394502000144-1-009124/2026-000001` -> `.../atas/00394502000144/2026/9124/1`."""
    m = ID_LINK.fullmatch(id_ata)
    if not m:
        return None
    cnpj, compra, ano, seq = m.groups()
    return f"{URL_PORTAL}/atas/{cnpj}/{ano}/{int(compra)}/{int(seq)}"


def validar_pagina(corpo: Any) -> tuple[list[dict[str, Any]], int, int]:
    """Envelope `{data, totalRegistros, totalPaginas}`; divergência é erro `contrato`."""
    if not isinstance(corpo, dict) or not isinstance(corpo.get("data"), list):
        raise ErroValidacao("contrato", "resposta da consulta de atas sem a lista `data`")
    totais = []
    for chave in ("totalRegistros", "totalPaginas"):
        valor = corpo.get(chave)
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
            raise ErroValidacao("contrato", f"resposta da consulta de atas sem `{chave}` inteiro")
        totais.append(valor)
    for item in corpo["data"]:
        if not isinstance(item, dict):
            raise ErroValidacao("contrato", "ata da consulta não é objeto")
        faltando = [c for c in CAMPOS_ITEM if c not in item]
        if faltando:
            raise ErroValidacao("contrato", f"ata da consulta sem os campos {faltando}")
    return corpo["data"], totais[0], totais[1]


def mapear(
    item: Mapping[str, Any], pads: Mapping[str, re.Pattern[str]], hoje: date
) -> AtaBusca | None | bool:
    """A ata de TI vigente; `None` se não deve estar na base; `False` se é ilegível.

    `None` (cancelada, vencida ou objeto sem termo) tira a ata da base; `False` (sem id, sem
    objeto ou sem vigência) só conta como descartada e não mexe no que já existe. A ata cuja
    vigência ainda não começou entra: é registro de preço válido já publicado.
    """
    id_ata = str(item.get("numeroControlePNCPAta") or "").strip()
    fim = busca._data(item.get("vigenciaFim"))
    objeto = _texto(item.get("objetoContratacao"))
    url = link(id_ata)
    if not ID_PNCP_ATA.fullmatch(id_ata) or url is None or fim is None or not objeto:
        return False
    if bool(item.get("cancelado")) or fim < hoje:
        return None
    termos = termos_que_casam(objeto, pads)
    if not termos:
        return None
    numero, ano = item.get("numeroAtaRegistroPreco"), item.get("anoAta")
    return AtaBusca(
        id_origem=id_ata,
        numero=_texto(f"Ata nº {numero}/{ano}" if numero and ano else numero) or id_ata,
        unidade_gerenciadora=_texto(item.get("nomeUnidadeOrgao")),
        orgao=_texto(item.get("nomeOrgao")),
        objeto=objeto,
        inicio=busca._data(item.get("vigenciaInicio")),
        fim=fim,
        status_origem=STATUS_ORIGEM,
        cancelada=False,
        link_origem=url,
        valor_total=None,
        esfera=None,
        uf=None,
        municipio=None,
        atualizado_em=_texto(item.get("dataAtualizacaoGlobal")),
        termos=termos,
    )


def ler_delta(
    itens: Sequence[Mapping[str, Any]], pads: Mapping[str, re.Pattern[str]], hoje: date
) -> Delta:
    """A versão mais nova de cada ata decide (a mesma ata pode vir mais de uma vez)."""
    d = Delta(lidos=len(itens))
    ordenados = sorted(itens, key=lambda i: str(i.get("dataAtualizacaoGlobal") or ""))
    for item in ordenados:
        ata = mapear(item, pads, hoje)
        if ata is False:
            d.descartados += 1
            continue
        id_ata = str(item["numeroControlePNCPAta"]).strip()
        d.versoes[id_ata] = str(item.get("dataAtualizacaoGlobal") or "")
        if ata is None:
            d.entram.pop(id_ata, None)
            d.unidades.pop(id_ata, None)
            d.saem.add(id_ata)
            continue
        d.saem.discard(id_ata)
        d.entram[id_ata] = ata
        if codigo := str(item.get("codigoUnidadeOrgao") or "").strip():
            d.unidades[id_ata] = codigo
    return d


def _base_mais_nova(base: AtaBusca | None, versao: str) -> bool:
    """A base já tem versão de data posterior (a API só dá a data; a busca dá também a hora)."""
    return base is not None and base.atualizado_em[:10] > versao[:10]


def aplicar(
    base: Mapping[str, AtaBusca],
    delta: Delta,
    pads: Mapping[str, re.Pattern[str]],
    hoje: date,
) -> tuple[dict[str, AtaBusca], dict[str, int]]:
    """Nova carga: a ativa (`base`) com o que a API trouxe por cima.

    Os termos da base são recalculados pela lista atual (termo removido tira a ata) e a
    vencida sai. Versão da API mais velha que a da base é ignorada: a semente leva horas e
    um delta pode ter publicado algo mais novo no meio.
    """
    atas: dict[str, AtaBusca] = {}
    for id_ata, a in base.items():
        if a.fim < hoje or a.cancelada:
            continue
        termos = termos_que_casam(a.objeto, pads)
        if termos:
            a.termos = termos
            atas[id_ata] = a
    mantidas = len(atas)
    antigas = removidas = novas = 0
    for id_ata in delta.saem:
        if _base_mais_nova(base.get(id_ata), delta.versoes.get(id_ata, "")):
            antigas += 1
        elif atas.pop(id_ata, None) is not None:
            removidas += 1
    for id_ata, nova in delta.entram.items():
        anterior = base.get(id_ata)
        if _base_mais_nova(anterior, delta.versoes.get(id_ata, "")):
            antigas += 1
            continue
        if anterior is None:
            novas += 1
        else:
            # O cadastro da unidade e o status do portal não vêm na consulta de atas.
            nova.esfera, nova.uf, nova.municipio = anterior.esfera, anterior.uf, anterior.municipio
            if anterior.status_origem:
                nova.status_origem = anterior.status_origem
        atas[id_ata] = nova
    contagens = {
        "atas_base": len(base),
        "atas_base_mantidas": mantidas,
        "atas_delta": len(delta.entram),
        "atas_novas": novas,
        "atas_removidas": removidas,
        "atas_versao_antiga": antigas,
    }
    return atas, contagens


async def _pegar(
    client: PNCPClient,
    limitador: LimitadorTaxa,
    rota: str,
    params: Mapping[str, str | int],
    telemetria: Telemetria,
) -> Any | None:
    """Uma página, com retry próprio sobre o `get_json` do compras-mcp (ADR 0004).

    `None` é janela vazia (HTTP 204, que o `get_json` vê como "não-JSON" vazio).
    """
    ultimo = ""
    for tentativa in range(1, TENTATIVAS + 1):
        await limitador.aguardar()
        falha: str | None
        try:
            corpo = await client.get_json(rota, dict(params), max_retries=0, timeout=TIMEOUT)
            telemetria.registrar(rota, None)
            return corpo
        except ComprasRateLimitError:
            falha = "http_429"
        except ComprasServerError:
            falha = "http_5xx"
        except ComprasTimeoutError:
            falha = "timeout"
        except ComprasHTTPError as exc:
            texto = str(exc)
            if "nao-JSON" in texto and texto.endswith(": "):
                telemetria.registrar(rota, None)
                return None
            if "Erro de transporte" not in texto:
                telemetria.registrar(rota, "contrato")
                raise ErroValidacao("contrato", f"consulta de atas: {texto[:200]}") from exc
            falha = "reset"
        except ComprasError as exc:  # 404 e afins: a rota mudou
            telemetria.registrar(rota, "contrato")
            raise ErroValidacao("contrato", f"consulta de atas: {type(exc).__name__}") from exc
        telemetria.registrar(rota, falha)
        ultimo = falha
        if tentativa < TENTATIVAS:
            await asyncio.sleep(min(ESPERA_BASE * 2 ** (tentativa - 1), ESPERA_MAXIMA))
    raise ErroValidacao(
        "rede", f"consulta de atas sem resposta depois de {TENTATIVAS} tentativas ({ultimo})"
    )


@dataclass(slots=True)
class Pagina:
    numero: int
    paginas: int  # total declarado nesta página (a lista pode crescer durante a leitura)
    declarado: int
    itens: list[dict[str, Any]]


async def paginas(
    client: PNCPClient,
    limitador: LimitadorTaxa,
    rota: str,
    filtros: Mapping[str, str],
    telemetria: Telemetria,
    primeira: int = 1,
) -> AsyncIterator[Pagina]:
    """Cada página de uma consulta, a partir de `primeira` (retomada da semente)."""
    pagina, total_paginas = primeira, primeira
    inicio = time.monotonic()
    while pagina <= total_paginas:
        corpo = await _pegar(
            client,
            limitador,
            rota,
            {**filtros, "pagina": pagina, "tamanhoPagina": TAMANHO_PAGINA},
            telemetria,
        )
        if corpo is None:
            if pagina == 1:
                return
            raise ErroValidacao("pagina_vazia", f"página {pagina} de {total_paginas} veio vazia")
        da_pagina, declarado, total_paginas = validar_pagina(corpo)
        if not da_pagina and declarado and pagina <= total_paginas:
            raise ErroValidacao("pagina_vazia", f"página {pagina} de {total_paginas} veio vazia")
        if pagina % PROGRESSO_A_CADA == 0 or pagina == total_paginas:
            gasto = time.monotonic() - inicio
            log.info(
                "pncp_atas_progresso",
                rota=rota,
                pagina=pagina,
                paginas=total_paginas,
                eta_min=round(gasto / (pagina - primeira + 1) * (total_paginas - pagina) / 60),
            )
        yield Pagina(pagina, total_paginas, declarado, da_pagina)
        pagina += 1


async def paginar(
    client: PNCPClient,
    limitador: LimitadorTaxa,
    rota: str,
    filtros: Mapping[str, str],
    telemetria: Telemetria,
) -> tuple[list[dict[str, Any]], int]:
    """Todas as páginas de uma consulta; devolve (itens, total declarado na 1ª página)."""
    itens: list[dict[str, Any]] = []
    declarado = 0
    async for p in paginas(client, limitador, rota, filtros, telemetria):
        if p.numero == 1:
            declarado = p.declarado
        itens.extend(p.itens)
    return itens, declarado


@dataclass(slots=True)
class Plano:
    motivo: str
    filtros: dict[str, str]
    janela_truncada: bool = False


def _dia(d: date) -> str:
    return d.strftime("%Y%m%d")


def planejar(marca: str | None, hoje: date) -> Plano:
    """Janela do delta: desde a marca d'água (menos a sobreposição) até hoje."""
    motivo, truncada = "delta", False
    try:
        desde = date.fromisoformat(marca) if marca else None
    except ValueError:
        desde, motivo = None, "marca_dagua_invalida"
    if desde is None:
        desde = hoje - timedelta(days=DIAS_SEM_MARCA)
        if motivo == "delta":
            motivo = "sem_marca_dagua"
    elif desde > hoje:
        desde, motivo = hoje - timedelta(days=DIAS_SEM_MARCA), "marca_dagua_futura"
    elif (hoje - desde).days > DIAS_MAXIMOS_DELTA:
        desde, motivo = hoje - timedelta(days=DIAS_MAXIMOS_DELTA), "marca_dagua_velha"
        truncada = True
    inicial = desde - timedelta(days=SOBREPOSICAO_DIAS)
    return Plano(motivo, {"dataInicial": _dia(inicial), "dataFinal": _dia(hoje)}, truncada)


def filtros_semente(hoje: date) -> dict[str, str]:
    """Vigentes hoje e as que começam em até um ano (a API cruza pela vigência)."""
    return {"dataInicial": _dia(hoje), "dataFinal": _dia(hoje + timedelta(days=VIGENCIA_DIAS))}


def resultados_por_termo(atas: Mapping[str, AtaBusca], termos: Sequence[str]) -> dict[str, int]:
    """Atas da carga por termo: o gancho da operação (`PNCP_TI_PNCP_TERMO`) lê daqui."""
    contagem = dict.fromkeys(termos, 0)
    for a in atas.values():
        for t in a.termos:
            if t in contagem:
                contagem[t] += 1
    return contagem


async def _ativa(conn: psycopg.AsyncConnection, hoje: date) -> dict[str, AtaBusca]:
    ativa = await (
        await conn.execute("SELECT id FROM cargas WHERE fonte = %s AND ativa", (FONTE,))
    ).fetchone()
    base = await busca._atas_ativas(conn, ativa["id"], hoje) if ativa else {}
    await conn.commit()  # a publicação abre a própria transação
    return base


async def _marca(conn: psycopg.AsyncConnection) -> str | None:
    """Marca d'água da última carga deste coletor, mesmo que a reserva tenha publicado depois.

    A carga da busca do portal (reserva) não lê o delta, mas também não desfaz o que ele
    leu: o próximo delta continua de onde a API parou.
    """
    linha = await (
        await conn.execute(
            "SELECT contagens->>'marca_dagua' AS marca FROM cargas WHERE fonte = %s "
            "AND status IN ('concluida', 'substituida') AND contagens->>'coletor' = %s "
            "ORDER BY concluido_em DESC NULLS LAST LIMIT 1",
            (FONTE, COLETOR),
        )
    ).fetchone()
    await conn.commit()
    return linha["marca"] if linha else None


async def _completar_unidades(
    conn: psycopg.AsyncConnection, atas: Mapping[str, AtaBusca], delta: Delta
) -> dict[str, int]:
    """Esfera, UF e município pelo cadastro de unidades (ADR 0034) para quem ainda não tem."""
    faltam = {i: delta.unidades[i] for i, a in atas.items() if a.uf is None and i in delta.unidades}
    chaves = {i: c for i, cod in faltam.items() if (c := unidades_pncp.chave(i, cod))}
    if not chaves:
        return {"unidades": 0}
    resolvidas, contagens = await unidades_pncp.resolver(conn, set(chaves.values()))
    for id_ata, c in chaves.items():
        u = resolvidas.get(c)
        if u is not None:
            a = atas[id_ata]
            a.esfera, a.uf, a.municipio = u.esfera, u.uf, u.municipio
    return contagens


def comparar(atas: Mapping[str, AtaBusca], base: Mapping[str, AtaBusca]) -> dict[str, int]:
    """Quanto a carga nova tem em comum com a ativa (eval de equivalência, ADR 0038)."""
    novas, antigas = set(atas), set(base)
    return {
        "comum_com_ativa": len(novas & antigas),
        "so_na_nova": len(novas - antigas),
        "so_na_ativa": len(antigas - novas),
    }


def _montar(
    base: Mapping[str, AtaBusca],
    delta: Delta,
    pads: Mapping[str, re.Pattern[str]],
    termos: Sequence[str],
    hoje: date,
    extra: Mapping[str, Any],
    declarado: int,
) -> Coleta:
    atas, contagens_merge = aplicar(base, delta, pads, hoje)
    contagens: dict[str, Any] = {
        "coletor": COLETOR,
        **extra,
        "termos": len(termos),
        "registros_declarados": declarado,
        "registros_lidos": delta.lidos,
        "registros_divergentes": abs(declarado - delta.lidos),
        "itens_descartados": delta.descartados,
        **contagens_merge,
        "atas_unicas": len(atas),
        "resultados_por_termo": resultados_por_termo(atas, termos),
        **comparar(atas, base),
    }
    return Coleta(atas, contagens, sem_resultado=[], falhos=[])


async def coletar(
    conn: psycopg.AsyncConnection,
    client: PNCPClient,
    termos: Sequence[str],
    hoje: date,
) -> tuple[Coleta, Delta]:
    """O delta da carga diária sobre a carga ativa."""
    marca = await _marca(conn)
    base = await _ativa(conn, hoje)
    plano = planejar(marca, hoje)
    log.info("pncp_atas_plano", motivo=plano.motivo, **plano.filtros)
    pads = padroes(termos)
    telemetria = Telemetria()
    limitador = LimitadorTaxa(REQUISICOES_POR_SEGUNDO)
    itens, declarado = await paginar(client, limitador, ROTA_DELTA, plano.filtros, telemetria)
    delta = ler_delta(itens, pads, hoje)
    extra = {
        "modo": "delta",
        "motivo_modo": plano.motivo,
        "janela": plano.filtros,
        "janela_truncada": plano.janela_truncada,
        "marca_dagua": hoje.isoformat(),
        **telemetria.contagens(),
    }
    return _montar(base, delta, pads, termos, hoje, extra, declarado), delta


class Checkpoint:
    """Páginas já lidas da semente, uma por linha (JSON), para retomar depois de uma queda.

    Guarda as atas cujo objeto casa algum termo e as que estão na base (para tirar a que deixou
    de casar), com os campos que `mapear` lê; a primeira linha identifica a varredura (janela,
    termos e data de início).
    """

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho

    @staticmethod
    def _termos_hash(termos: Sequence[str]) -> str:
        return hashlib.sha256("\n".join(termos).encode()).hexdigest()[:12]

    def abrir(
        self, filtros: Mapping[str, str], termos: Sequence[str], hoje: date
    ) -> tuple[dict[str, Any], list[dict[str, Any]], int, int, int, int]:
        """(cabeçalho, atas guardadas, próxima página, total de páginas, lidos, declarados).

        Retoma se o checkpoint é da mesma lista de termos e tem até `DIAS_CHECKPOINT` dias; a
        janela continua a do início, para a paginação não mudar no meio da varredura.
        """
        try:
            linhas = self.caminho.read_text(encoding="utf-8").splitlines()
            cab = json.loads(linhas[0])
            idade = (hoje - date.fromisoformat(cab["inicio"])).days
            if cab["termos"] == self._termos_hash(termos) and 0 <= idade <= DIAS_CHECKPOINT:
                itens: list[dict[str, Any]] = []
                proxima, total, lidos, declarado = 1, 0, 0, 0
                for linha in linhas[1:]:
                    try:
                        p = json.loads(linha)
                    except ValueError:  # linha cortada pela queda: refaz essa página
                        break
                    itens.extend(p["itens"])
                    proxima, total = p["pagina"] + 1, p["paginas"]
                    lidos += p["lidos"]
                    declarado = declarado or p["declarado"]
                self._reescrever(cab, linhas[1:proxima])
                return cab, itens, proxima, total, lidos, declarado
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            pass
        cab = {"filtros": dict(filtros), "termos": self._termos_hash(termos)}
        cab["inicio"] = hoje.isoformat()
        self._reescrever(cab, [])
        return cab, [], 1, 0, 0, 0

    def _reescrever(self, cab: Mapping[str, Any], linhas: Sequence[str]) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        provisorio = self.caminho.with_suffix(".tmp")
        provisorio.write_text(
            "".join(f"{x}\n" for x in [json.dumps(cab), *linhas]), encoding="utf-8"
        )
        provisorio.replace(self.caminho)

    def gravar(self, p: Pagina, guardados: list[dict[str, Any]]) -> None:
        linha = {
            "pagina": p.numero,
            "paginas": p.paginas,
            "lidos": len(p.itens),
            "declarado": p.declarado,
        }
        with self.caminho.open("a", encoding="utf-8") as f:
            f.write(json.dumps({**linha, "itens": guardados}, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def apagar(self) -> None:
        self.caminho.unlink(missing_ok=True)


async def _travar_esperando(conn: psycopg.AsyncConnection) -> None:
    """Trava de sessão da fonte, esperando a carga diária terminar (até ~1h30)."""
    for tentativa in range(TENTATIVAS_TRAVA):
        if await tentar_trava_sessao(conn, busca.CHAVE_TRAVA):
            return
        if tentativa == 0:
            log.info("pncp_atas_semente_esperando_trava")
        await asyncio.sleep(ESPERA_TRAVA)
    raise ErroValidacao("concorrente", "a carga da fonte não soltou a trava para a semente")


async def coletar_semente(
    conn: psycopg.AsyncConnection,
    client: PNCPClient,
    termos: Sequence[str],
    hoje: date,
    checkpoint: Checkpoint,
    travar: bool = True,
) -> tuple[Coleta, Delta]:
    """A varredura completa, com retomada.

    Lê as páginas sem a trava da fonte; no fim pega a trava de sessão (que vale até a
    publicação), relê o que mudou desde o início da varredura pelo delta e só então lê a base.
    Assim a versão lida horas antes não desfaz o que um delta publicou no meio.
    """
    pads = padroes(termos)
    na_base = set(await _ativa(conn, hoje))
    cab, guardados, proxima, total, lidos, declarado = checkpoint.abrir(
        filtros_semente(hoje), termos, hoje
    )
    filtros = cab["filtros"]
    log.info("pncp_atas_semente", retomada_na_pagina=proxima, inicio=cab["inicio"], **filtros)
    telemetria = Telemetria()
    limitador = LimitadorTaxa(REQUISICOES_POR_SEGUNDO)
    retomadas = 0
    while not (total and proxima > total):  # checkpoint completo: só falta publicar
        try:
            async for p in paginas(
                client, limitador, ROTA_VIGENCIA, filtros, telemetria, primeira=proxima
            ):
                casam = [
                    {c: i.get(c) for c in CAMPOS_GUARDADOS}
                    for i in p.itens
                    if str(i.get("numeroControlePNCPAta") or "").strip() in na_base
                    or termos_que_casam(_texto(i.get("objetoContratacao")), pads)
                ]
                checkpoint.gravar(p, casam)
                guardados.extend(casam)
                lidos += len(p.itens)
                declarado = declarado or p.declarado
                proxima, total = p.numero + 1, p.paginas
            break
        except ErroValidacao as exc:
            if exc.tipo != "rede" or retomadas >= RETOMADAS:
                raise
            retomadas += 1
            log.warning("pncp_atas_retomada", pagina=proxima, retomada=retomadas)
            await asyncio.sleep(ESPERA_RETOMADA)
    if travar:
        await _travar_esperando(conn)
    # O que mudou desde a véspera do início vem por último: na mesma data, vale o delta.
    inicio = date.fromisoformat(cab["inicio"]) - timedelta(days=SOBREPOSICAO_DIAS)
    janela = {"dataInicial": _dia(inicio), "dataFinal": _dia(hoje)}
    recentes, _ = await paginar(client, limitador, ROTA_DELTA, janela, telemetria)
    delta = ler_delta([*guardados, *recentes], pads, hoje)
    delta.lidos = lidos
    marca = await _marca(conn)
    base = await _ativa(conn, hoje)
    extra = {
        "modo": "semente",
        "motivo_modo": "semente",
        "janela": filtros,
        "janela_recuperacao": janela,
        "registros_recuperacao": len(recentes),
        "retomadas": retomadas,
        # A semente não lê o delta: mantém a marca d'água anterior para não abrir buraco.
        "marca_dagua": marca or cab["inicio"],
        **telemetria.contagens(),
    }
    return _montar(base, delta, pads, termos, hoje, extra, declarado), delta


async def principal(
    validar_apenas: bool,
    semente: bool,
    termos_arquivo: Path = busca.ARQUIVO_TERMOS,
    checkpoint: Checkpoint | None = None,
) -> int:
    conn: psycopg.AsyncConnection | None = None
    carga_id: UUID = uuid4()
    geracao: dict[str, dict[str, object]] = {}
    contagens: dict[str, Any] = {}
    inicio = time.monotonic()
    checkpoint = checkpoint or Checkpoint(ARQUIVO_CHECKPOINT)
    try:
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        termos = busca.ler_termos(termos_arquivo)
        # A semente leva horas e só pega a trava da fonte no fim (a carga diária roda no meio).
        trava = not (validar_apenas or semente)
        conn = await (busca._conectar_com_trava() if trava else conectar(get_settings()))
        try:
            async with PNCPClient(base_url=URL_CONSULTA, timeout=TIMEOUT, max_retries=0) as client:
                if semente:
                    coleta, delta = await coletar_semente(
                        conn, client, termos, hoje, checkpoint, travar=not validar_apenas
                    )
                else:
                    coleta, delta = await coletar(conn, client, termos, hoje)
            contagens = coleta.contagens
            geracao = busca._geracao(coleta, termos)
            busca.validar(coleta)
            if validar_apenas:
                log.info(
                    "pncp_atas_validada", segundos=round(time.monotonic() - inicio), **contagens
                )
                return 0
            contagens.update(await _completar_unidades(conn, coleta.atas, delta))
            resultado = await busca.publicar(conn, coleta, geracao, carga_id, hoje)
            if semente:
                checkpoint.apagar()
        except Exception as exc:
            if not validar_apenas:
                await _registrar_falha(conn, carga_id, exc, geracao, FONTE, contagens)
            raise
        log.info(
            "pncp_atas_carga",
            carga_id=str(resultado.carga_id),
            status=resultado.status,
            segundos=round(time.monotonic() - inicio),
            **resultado.contagens,
        )
        return 0 if await atualizar_busca(conn) else 1
    except ErroValidacao as exc:
        log.error("pncp_atas_falha", tipo=exc.tipo, mensagem=str(exc))
        return busca.codigo_saida(exc)
    except Exception as exc:
        log.error(
            "pncp_atas_falha", tipo=type(exc).__name__, sqlstate=getattr(exc, "sqlstate", None)
        )
        return 1
    finally:
        if conn is not None:
            await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Atas vigentes de TI pela API oficial do PNCP.")
    parser.add_argument("--validar", action="store_true", help="coleta e compara, sem gravar")
    parser.add_argument(
        "--semente", action="store_true", help="varredura completa, com retomada (unit mensal)"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(principal(args.validar, args.semente)))


if __name__ == "__main__":
    main()
