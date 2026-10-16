"""Busca do portal PNCP por termos de TI (R3, ADR 0016).

Uma consulta paginada por termo de `insumos/termos_ti.txt` (`tipos_documento=ata`,
`status=vigente`), dedupe por `numero_controle_pncp` e troca atômica da carga `pncp_busca`.
A API de busca não é documentada: o contrato é validado a cada resposta e uma mudança
falha alto. A busca não traz itens nem preços; o ARP tem preferência na view quando a mesma
ata existe nas duas fontes (migração 0007).

    python -m pncp_ti.fontes.pncp_busca             # busca e carrega
    python -m pncp_ti.fontes.pncp_busca --validar   # busca e valida, sem gravar
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import psycopg
import structlog

from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes.siga import _copiar, _registrar_falha, tentar_trava_sessao
from pncp_ti.fontes.siga_csv import ErroValidacao
from pncp_ti.ingest.rate_limit import LimitadorTaxa
from pncp_ti.privacy import sanitizar

FONTE = "pncp_busca"
CHAVE_TRAVA = "carga:pncp_busca"
URL_BUSCA = "https://pncp.gov.br/api/search/"
URL_PORTAL = "https://pncp.gov.br/app"
ARQUIVO_TERMOS = Path(__file__).resolve().parents[3] / "insumos" / "termos_ti.txt"
TAMANHO_PAGINA = 500
LIMITE_JANELA = 10_000  # o índice de busca não pagina além disso por consulta
REQUISICOES_POR_SEGUNDO = 2.0
TENTATIVAS = 6
ESPERA_BASE = 2.0
PISO_ATAS = 0.5
PASSADAS_EXTRA = 2  # novas tentativas dos termos que falharam, depois da passada principal
ESPERA_PASSADA = 60.0  # segundos antes de cada passada extra: o portal costuma voltar em minutos
LIMITE_BYTES = 25 * 1024 * 1024  # uma página de 500 atas tem ~2 MB
ID_PNCP_ATA = re.compile(r"\d{14}-\d-\d{6}/\d{4}-\d{6}")
LIMITE_TEXTO = 4000
CAMPOS_ITEM = (
    "numero_controle_pncp",
    "description",
    "data_fim_vigencia",
    "item_url",
    "orgao_nome",
)
ERROS_DETERMINISTICOS = frozenset({"contrato", "sem_atas", "queda_volume", "geracao_antiga"})
SAIDA_DETERMINISTICA = 2

log = structlog.get_logger()


@dataclass(slots=True)
class AtaBusca:
    id_origem: str  # numero_controle_pncp
    numero: str
    unidade_gerenciadora: str
    orgao: str
    objeto: str
    inicio: date | None
    fim: date
    status_origem: str
    cancelada: bool
    link_origem: str
    valor_total: Decimal | None
    esfera: str | None
    uf: str | None
    municipio: str | None
    atualizado_em: str
    termos: set[str] = field(default_factory=set)

    @property
    def vigente_na_origem(self) -> bool:
        return not self.cancelada

    @property
    def motivo_ti(self) -> str:
        return ("termo_pncp:" + "|".join(sorted(self.termos)))[:500]


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    carga_id: UUID
    status: str
    contagens: dict[str, Any]


def ler_termos(caminho: Path = ARQUIVO_TERMOS) -> list[str]:
    termos: list[str] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        termo = " ".join(linha.split())
        if termo and not termo.startswith("#") and termo not in termos:
            termos.append(termo)
    if not termos:
        raise ErroValidacao("contrato", f"{caminho.name} não tem nenhum termo")
    return termos


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )


def casa_termo(objeto: str, termo: str) -> bool:
    """O termo inteiro, como sequência de palavras, aparece no objeto (sem acento nem caixa).

    O portal casa por palavra solta (`equipamentos de informatica` devolve 32 mil atas, a
    maioria de mobiliário e obras). Sem este filtro a carga publicaria ruído como "TI".
    A última palavra aceita sufixo (notebook → notebooks).
    """
    palavras = [re.escape(p) for p in _sem_acento(termo).split()]
    if not palavras:
        return False
    padrao = r"\b" + r"\W+".join(palavras) + r"\w*"
    return re.search(padrao, _sem_acento(objeto)) is not None


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return " ".join(str(sanitizar(str(valor))).split())[:LIMITE_TEXTO]


def _data(valor: Any) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _decimal(valor: Any) -> Decimal | None:
    if valor is None or isinstance(valor, bool) or valor == "":
        return None
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


def validar_pagina(corpo: Any) -> tuple[list[dict[str, Any]], int]:
    """Confere o contrato da resposta; qualquer divergência é erro `contrato`."""
    if not isinstance(corpo, dict) or not isinstance(corpo.get("items"), list):
        raise ErroValidacao("contrato", "resposta da busca sem a lista `items`")
    total = corpo.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ErroValidacao("contrato", "resposta da busca sem `total` inteiro")
    for item in corpo["items"]:
        if not isinstance(item, dict):
            raise ErroValidacao("contrato", "item da busca não é objeto")
        faltando = [c for c in CAMPOS_ITEM if c not in item]
        if faltando:
            raise ErroValidacao("contrato", f"item da busca sem os campos {faltando}")
    return corpo["items"], total


def mapear(item: dict[str, Any], termo: str, hoje: date) -> AtaBusca | None:
    """Converte um item da busca; devolve `None` para o que não é ata vigente identificável."""
    id_origem = str(item.get("numero_controle_pncp") or "").strip()
    fim = _data(item.get("data_fim_vigencia"))
    if not ID_PNCP_ATA.fullmatch(id_origem) or fim is None or fim < hoje:
        return None
    caminho = str(item.get("item_url") or "")
    if not caminho.startswith("/atas/"):
        return None
    objeto = _texto(item.get("description"))
    if not objeto:
        return None
    return AtaBusca(
        id_origem=id_origem,
        numero=_texto(item.get("title")) or id_origem,
        unidade_gerenciadora=_texto(item.get("unidade_nome")),
        orgao=_texto(item.get("orgao_nome")),
        objeto=objeto,
        inicio=_data(item.get("data_inicio_vigencia")),
        fim=fim,
        status_origem=_texto(item.get("situacao_nome")),
        cancelada=bool(item.get("cancelado")),
        link_origem=URL_PORTAL + caminho,
        valor_total=_decimal(item.get("valor_global")),
        esfera=_texto(item.get("esfera_nome")) or None,
        uf=_texto(item.get("uf")) or None,
        municipio=_texto(item.get("municipio_nome")) or None,
        atualizado_em=_texto(item.get("data_atualizacao_pncp")),
        termos={termo},
    )


async def _pegar(
    client: httpx.AsyncClient, limitador: LimitadorTaxa, params: Mapping[str, str | int]
) -> Any:
    """GET com retry/backoff: o portal derruba conexões e responde vazio de forma intermitente."""
    ultimo: str = ""
    for tentativa in range(1, TENTATIVAS + 1):
        await limitador.aguardar()
        try:
            async with client.stream("GET", URL_BUSCA, params=params) as resposta:
                if resposta.status_code == 200:
                    corpo = bytearray()
                    async for bloco in resposta.aiter_bytes(1 << 16):
                        corpo.extend(bloco)
                        if len(corpo) > LIMITE_BYTES:
                            raise ErroValidacao("contrato", "resposta da busca acima do limite")
                    return json.loads(corpo)
                ultimo = f"HTTP {resposta.status_code}"
            if resposta.status_code < 500 and resposta.status_code != 429:
                raise ErroValidacao("contrato", f"busca respondeu {ultimo}")
        except (httpx.TransportError, json.JSONDecodeError) as exc:
            ultimo = type(exc).__name__
        if tentativa < TENTATIVAS:
            await asyncio.sleep(ESPERA_BASE * 2 ** (tentativa - 1))
    raise _TermoFalhou(ultimo)


class _TermoFalhou(Exception):
    pass


async def buscar_termo(
    client: httpx.AsyncClient, limitador: LimitadorTaxa, termo: str
) -> tuple[list[dict[str, Any]], int]:
    """Todas as páginas de um termo; devolve (itens, total declarado)."""
    itens: list[dict[str, Any]] = []
    total = 0
    pagina = 1
    while True:
        corpo = await _pegar(
            client,
            limitador,
            {
                "q": termo,
                "tipos_documento": "ata",
                "status": "vigente",
                "tam_pagina": TAMANHO_PAGINA,
                "pagina": pagina,
            },
        )
        da_pagina, total_pagina = validar_pagina(corpo)
        if pagina == 1:
            total = total_pagina  # o total da 1ª página é a referência; as seguintes não o mudam
        itens.extend(da_pagina)
        esperado = min(total, LIMITE_JANELA)
        if len(itens) >= esperado:
            return itens, total
        if not da_pagina:
            # Resposta vazia antes do total declarado: o portal falhou; não é fim de lista.
            raise _TermoFalhou(f"página vazia com {len(itens)} de {esperado} itens")
        pagina += 1


async def _coletar_termo(
    client: httpx.AsyncClient,
    limitador: LimitadorTaxa,
    termo: str,
    hoje: date,
    atas: dict[str, AtaBusca],
    contagens: dict[str, Any],
    sem_resultado: list[str],
    totais: dict[str, int],
) -> bool:
    """Busca um termo e acumula as atas que o casam; `False` se o portal não respondeu."""
    try:
        itens, total = await buscar_termo(client, limitador, termo)
    except _TermoFalhou as exc:
        log.warning("pncp_busca_termo_falhou_tentativa", termo=termo, motivo=str(exc))
        return False
    totais[termo] = total
    contagens["itens_lidos"] += len(itens)
    if total > LIMITE_JANELA:
        contagens["termos_truncados"] += 1
        log.warning("pncp_busca_termo_truncado", termo=termo, total=total)
    if total == 0:
        contagens["termos_sem_resultado"] += 1
        sem_resultado.append(termo)
        log.warning("pncp_busca_termo_sem_resultado", termo=termo)
    aceitos = 0
    for item in itens:
        ata = mapear(item, termo, hoje)
        if ata is None:
            contagens["itens_descartados"] += 1
        elif not casa_termo(ata.objeto, termo):
            contagens["itens_sem_termo"] += 1
        elif ata.id_origem in atas:
            atas[ata.id_origem].termos.add(termo)
            aceitos += 1
        else:
            atas[ata.id_origem] = ata
            aceitos += 1
    log.info("pncp_busca_termo", termo=termo, total=total, lidos=len(itens), aceitos=aceitos)
    return True


@dataclass(slots=True)
class Coleta:
    atas: dict[str, AtaBusca]
    contagens: dict[str, Any]
    sem_resultado: list[str]


async def coletar(
    termos: Sequence[str], hoje: date, client: httpx.AsyncClient | None = None
) -> Coleta:
    limitador = LimitadorTaxa(REQUISICOES_POR_SEGUNDO)
    proprio = client is None
    client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(30.0), headers={"Accept": "application/json"}
    )
    atas: dict[str, AtaBusca] = {}
    contagens = {
        "termos": len(termos),
        "termos_falhos": 0,
        "termos_sem_resultado": 0,
        "termos_truncados": 0,
        "itens_lidos": 0,
        "itens_descartados": 0,
        "itens_sem_termo": 0,
        "termos_recuperados": 0,
    }
    sem_resultado: list[str] = []
    totais: dict[str, int] = {}
    try:
        falhos: list[str] = []
        for termo in termos:
            if not await _coletar_termo(
                client, limitador, termo, hoje, atas, contagens, sem_resultado, totais
            ):
                falhos.append(termo)
        # Segunda chance: o portal falha de forma intermitente e costuma voltar minutos depois.
        for _ in range(PASSADAS_EXTRA):
            if not falhos:
                break
            await asyncio.sleep(ESPERA_PASSADA)
            ainda: list[str] = []
            for termo in falhos:
                if await _coletar_termo(
                    client, limitador, termo, hoje, atas, contagens, sem_resultado, totais
                ):
                    contagens["termos_recuperados"] += 1
                else:
                    ainda.append(termo)
            falhos = ainda
        for termo in falhos:
            contagens["termos_falhos"] += 1
            log.warning("pncp_busca_termo_falhou", termo=termo)
    finally:
        if proprio:
            await client.aclose()
    contagens["atas_unicas"] = len(atas)
    # Total declarado pelo portal por termo (antes do filtro de frase): o alerta da R6 lê daqui.
    contagens["resultados_por_termo"] = totais
    return Coleta(atas, contagens, sem_resultado)


def validar(coleta: Coleta) -> None:
    c = coleta.contagens
    if c["termos_falhos"]:
        # Termo perdido = atas exclusivas dele somem: não publica lista incompleta (o snapshot
        # anterior continua visível e a carga seguinte tenta de novo).
        raise ErroValidacao(
            "termos_falhos", f"{c['termos_falhos']} de {c['termos']} termos falharam"
        )
    if not coleta.atas:
        raise ErroValidacao("sem_atas", "a busca não devolveu nenhuma ata vigente")


def _geracao(coleta: Coleta, termos: Sequence[str]) -> dict[str, dict[str, object]]:
    resumo = hashlib.sha256()
    for id_origem in sorted(coleta.atas):
        resumo.update(f"{id_origem}\x1f{coleta.atas[id_origem].atualizado_em}\x1e".encode())
    termos_hash = hashlib.sha256("\n".join(termos).encode()).hexdigest()[:12]
    return {
        "atas": {"unicas": len(coleta.atas), "sha256": resumo.hexdigest()},
        "_termos": {"quantidade": len(termos), "sha256": termos_hash},
    }


async def publicar(
    conn: psycopg.AsyncConnection,
    coleta: Coleta,
    geracao: dict[str, dict[str, object]],
    carga_id: UUID,
    hoje: date,
) -> ResultadoCarga:
    contagens = coleta.contagens
    async with conn.transaction():
        bloqueio = await (
            await conn.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS ok", (CHAVE_TRAVA,)
            )
        ).fetchone()
        if not bloqueio["ok"]:
            raise ErroValidacao("concorrente", "outra carga da busca PNCP está em andamento")
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
            anteriores = int(ativa["contagens"].get("atas_unicas", 0))
            if anteriores and contagens["atas_unicas"] < PISO_ATAS * anteriores:
                raise ErroValidacao(
                    "queda_volume",
                    f"atas_unicas: {contagens['atas_unicas']} contra {anteriores} na carga ativa",
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
                    None,
                    a.inicio,
                    a.fim,
                    None,
                    a.status_origem,
                    [],
                    True,
                    a.motivo_ti,
                    a.vigente_na_origem,
                    a.id_origem,
                    a.link_origem,
                    a.orgao,
                    a.valor_total,
                    None,
                    a.atualizado_em or None,
                    a.esfera,
                    a.uf,
                    a.municipio,
                )
                for a in coleta.atas.values()
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


def codigo_saida(exc: ErroValidacao) -> int:
    """2 para erro que se repetiria igual numa nova tentativa; 1 se não."""
    return SAIDA_DETERMINISTICA if exc.tipo in ERROS_DETERMINISTICOS else 1


async def _conectar_com_trava() -> psycopg.AsyncConnection:
    conn = await conectar(get_settings())
    if not await tentar_trava_sessao(conn, CHAVE_TRAVA):
        await conn.close()
        raise ErroValidacao("concorrente", "outra execução da busca PNCP já está em andamento")
    return conn


async def principal(validar_apenas: bool, termos_arquivo: Path = ARQUIVO_TERMOS) -> int:
    conn: psycopg.AsyncConnection | None = None
    carga_id = uuid4()
    geracao: dict[str, dict[str, object]] = {}
    inicio = time.monotonic()
    try:
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        termos = ler_termos(termos_arquivo)
        conn = await (conectar(get_settings()) if validar_apenas else _conectar_com_trava())
        try:
            coleta = await coletar(termos, hoje)
            geracao = _geracao(coleta, termos)
            validar(coleta)
            if validar_apenas:
                log.info(
                    "pncp_busca_validada",
                    segundos=round(time.monotonic() - inicio),
                    **coleta.contagens,
                )
                return 0
            resultado = await publicar(conn, coleta, geracao, carga_id, hoje)
        except Exception as exc:
            if not validar_apenas:
                await _registrar_falha(conn, carga_id, exc, geracao, FONTE)
            raise
        log.info(
            "pncp_busca_carga",
            carga_id=str(resultado.carga_id),
            status=resultado.status,
            segundos=round(time.monotonic() - inicio),
            **resultado.contagens,
        )
        return 0
    except ErroValidacao as exc:
        log.error("pncp_busca_falha", tipo=exc.tipo, mensagem=str(exc))
        return codigo_saida(exc)
    except Exception as exc:
        log.error(
            "pncp_busca_falha", tipo=type(exc).__name__, sqlstate=getattr(exc, "sqlstate", None)
        )
        return 1
    finally:
        if conn is not None:
            await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Busca PNCP de atas vigentes por termos de TI.")
    parser.add_argument("--validar", action="store_true", help="busca e valida sem gravar")
    raise SystemExit(asyncio.run(principal(parser.parse_args().validar)))


if __name__ == "__main__":
    main()
