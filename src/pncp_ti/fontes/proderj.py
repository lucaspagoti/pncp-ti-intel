"""Links das contratações do PRODERJ: o endereço da página no site do órgão (ADR 0042).

O PRODERJ não tem API. O site publica as licitações em seis listas (`homologadas`, `andamento`,
`realizadas`, `canceladas`, `desertas`, `fracassadas`), cada processo numa página `node/N` cujo
título traz o número do processo SEI. Esta carga lê as listas, casa o processo SEI com o das atas
do SIGA e grava só o endereço (`proderj_links`). Vigência, órgão e itens continuam vindo do SIGA.

A troca é atômica, como nas outras fontes: uma falha deixa os links anteriores no ar.

    python -m pncp_ti.fontes.proderj             # lê o site e grava
    python -m pncp_ti.fontes.proderj --validar   # lê e conta, sem gravar
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import psycopg
import structlog

from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes.siga import _registrar_falha, tentar_trava_sessao
from pncp_ti.fontes.siga_csv import ErroValidacao

FONTE = "proderj"
URL_BASE = "https://www.rj.gov.br"
URL_NODE = URL_BASE + "/proderj/node/{}"
# Da mais para a menos prioritária: o mesmo processo SEI pode aparecer em duas listas (um pregão
# fracassado e refeito), e a homologada é a que originou a ata.
LISTAS = ("homologadas", "andamento", "realizadas", "canceladas", "desertas", "fracassadas")
POR_PAGINA = 50
MAX_PAGINAS = 10  # por lista; a maior (realizadas) tem 4 páginas de 50
LIMITE_BYTES = 8 * 1024 * 1024
TENTATIVAS = 3
TIMEOUT = 30.0
PISO_RELATIVO = 0.5
CHAVE_TRAVA = "carga:proderj"
CLIENTE = "pncp-ti-intel/1.0"  # nome genérico, sem dados do dono

log = structlog.get_logger()

_PROCESSO = re.compile(r"(430002)\s*/\s*0*(\d+)\s*/+\s*(\d{4})", re.ASCII)
# O título de cada processo, no campo `views-field-title` da lista; o resto da página (menu,
# rodapé, corpo do resumo) não entra, e uma mudança de marcação vira erro de contrato.
_LINK = re.compile(
    r'views-field-title"[^>]*>\s*<span class="field-content">\s*'
    r'<a\s[^>]*href="[^"]*?/node/(\d+)"[^>]*>(.*?)</a>',
    re.S,
)
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class Entrada:
    node_id: int
    titulo: str
    lista: str


@dataclass(frozen=True, slots=True)
class Link:
    processo: str
    node_id: int
    url: str
    titulo: str
    lista: str


def normalizar_processo(texto: str | None) -> str | None:
    """`SEI-430002/000030/2024` -> `430002/30/2024`; mesma regra de `proderj_processo()` (0012)."""
    achado = _PROCESSO.search(texto or "")
    if not achado:
        return None
    numero = achado.group(2).lstrip("0")
    return f"{achado.group(1)}/{numero}/{achado.group(3)}" if numero else None


def extrair_lista(pagina: str, lista: str) -> tuple[list[Entrada], bool]:
    """Processos de uma página de lista e se há uma próxima (`pager__item--next`)."""
    entradas: dict[int, Entrada] = {}
    for achado in _LINK.finditer(pagina):
        titulo = " ".join(html.unescape(_TAGS.sub(" ", achado.group(2))).split())
        node = int(achado.group(1))
        if titulo and node not in entradas:
            entradas[node] = Entrada(node, titulo, lista)
    return list(entradas.values()), "pager__item--next" in pagina


def consolidar(entradas: list[Entrada]) -> dict[str, Link]:
    """Um link por processo SEI: a lista de maior prioridade e, nela, o `node` mais novo."""
    escolhidos: dict[str, Link] = {}
    for e in entradas:
        processo = normalizar_processo(e.titulo)
        if processo is None:
            continue
        atual = escolhidos.get(processo)
        chave = (LISTAS.index(e.lista), -e.node_id)
        if atual is None or chave < (LISTAS.index(atual.lista), -atual.node_id):
            escolhidos[processo] = Link(
                processo, e.node_id, URL_NODE.format(e.node_id), e.titulo[:400], e.lista
            )
    return escolhidos


class _Transitorio(Exception):
    pass


async def _baixar(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> str:
    ultimo: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            async with client.stream("GET", url, params=params) as resposta:
                if resposta.status_code >= 500:
                    raise _Transitorio(f"HTTP {resposta.status_code}")
                if resposta.status_code != 200:
                    raise ErroValidacao("http", f"{url}: HTTP {resposta.status_code}")
                corpo = bytearray()
                async for bloco in resposta.aiter_bytes(1 << 16):
                    corpo += bloco
                    if len(corpo) > LIMITE_BYTES:
                        raise ErroValidacao("tamanho", f"{url}: acima do limite")
            return corpo.decode("utf-8", errors="replace")
        except (_Transitorio, httpx.TransportError) as exc:
            ultimo = exc
            log.warning("proderj_retry", url=url, tentativa=tentativa, erro=str(exc)[:120])
            if tentativa < TENTATIVAS:
                await asyncio.sleep(2.0 * tentativa)
    raise ErroValidacao("rede", f"{url}: falhou após {TENTATIVAS} tentativas: {ultimo}")


async def ler_site(
    client: httpx.AsyncClient,
    baixar: Callable[..., Awaitable[str]] = _baixar,
) -> list[Entrada]:
    """Percorre as seis listas, página a página, até acabar a paginação."""
    entradas: list[Entrada] = []
    for lista in LISTAS:
        for numero in range(MAX_PAGINAS):
            pagina = await baixar(
                client,
                f"{URL_BASE}/proderj/{lista}",
                {"items_per_page": str(POR_PAGINA), "page": str(numero)},
            )
            achadas, ha_proxima = extrair_lista(pagina, lista)
            entradas += achadas
            if not achadas or not ha_proxima:
                break
        else:
            raise ErroValidacao("contrato", f"lista {lista}: mais de {MAX_PAGINAS} páginas")
    return entradas


def validar(entradas: list[Entrada]) -> dict[str, Link]:
    """Contrato mínimo do site: a lista de homologadas nunca fica vazia; sem isso, o HTML mudou."""
    if not any(e.lista == "homologadas" for e in entradas):
        raise ErroValidacao("contrato", "nenhum processo na lista de homologadas")
    links = consolidar(entradas)
    if not links:
        raise ErroValidacao("contrato", "nenhum processo SEI reconhecido nos títulos")
    return links


async def publicar(
    conn: psycopg.AsyncConnection, links: dict[str, Link], entradas: int, carga_id: UUID
) -> dict[str, int]:
    contagens = {"entradas": entradas, "processos": len(links)}
    async with conn.transaction():
        bloqueio = await (
            await conn.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS ok", (CHAVE_TRAVA,)
            )
        ).fetchone()
        if not bloqueio["ok"]:
            raise ErroValidacao("concorrente", "outra carga do PRODERJ está em andamento")
        ativa = await (
            await conn.execute(
                "SELECT id, contagens FROM cargas WHERE fonte = %s AND ativa", (FONTE,)
            )
        ).fetchone()
        anteriores = int((ativa or {"contagens": {}})["contagens"].get("processos", 0))
        if anteriores and len(links) < PISO_RELATIVO * anteriores:
            raise ErroValidacao(
                "queda_volume", f"processos: {len(links)} contra {anteriores} na carga ativa"
            )
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        await conn.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status) "
            "VALUES (%s, %s, %s, 'em_andamento')",
            (carga_id, FONTE, hoje),
        )
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO proderj_links (carga_id, processo, node_id, url, titulo, lista) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (carga_id, k.processo, k.node_id, k.url, k.titulo, k.lista)
                    for k in links.values()
                ],
            )
        if ativa:
            await conn.execute(
                "UPDATE cargas SET ativa = false, status = 'substituida' WHERE id = %s",
                (ativa["id"],),
            )
            await conn.execute("DELETE FROM proderj_links WHERE carga_id = %s", (ativa["id"],))
        await conn.execute(
            "UPDATE cargas SET ativa = true, status = 'concluida', concluido_em = now(), "
            "contagens = %s WHERE id = %s",
            (json.dumps(contagens), carga_id),
        )
    return contagens


async def carregar(conn: psycopg.AsyncConnection, client: httpx.AsyncClient) -> dict[str, int]:
    """Lê o site e publica; qualquer falha fica em `cargas` e deixa os links anteriores no ar."""
    carga_id = uuid4()
    try:
        entradas = await ler_site(client)
        return await publicar(conn, validar(entradas), len(entradas), carga_id)
    except Exception as exc:
        await _registrar_falha(conn, carga_id, exc, {}, fonte=FONTE)
        raise


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": CLIENTE}
    )


async def principal(argumentos: argparse.Namespace) -> int:
    conn: psycopg.AsyncConnection | None = None
    try:
        async with _cliente() as client:
            if argumentos.validar:
                entradas = await ler_site(client)
                links = validar(entradas)
                por_lista: dict[str, int] = {}
                for k in links.values():
                    por_lista[k.lista] = por_lista.get(k.lista, 0) + 1
                log.info(
                    "proderj_validado", entradas=len(entradas), processos=len(links), **por_lista
                )
                return 0
            conn = await conectar(get_settings())
            if not await tentar_trava_sessao(conn, CHAVE_TRAVA):
                raise ErroValidacao("concorrente", "outra execução do PRODERJ já está rodando")
            contagens = await carregar(conn, client)
            log.info("proderj_carga", **contagens)
            return 0
    except ErroValidacao as exc:
        log.error("proderj_falha", tipo=exc.tipo, mensagem=str(exc))
        return 1
    except Exception as exc:
        log.error("proderj_falha", tipo=type(exc).__name__, sqlstate=getattr(exc, "sqlstate", None))
        return 1
    finally:
        if conn is not None:
            await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Links das contratações no site do PRODERJ.")
    parser.add_argument("--validar", action="store_true", help="lê o site e conta, sem gravar")
    raise SystemExit(asyncio.run(principal(parser.parse_args())))


if __name__ == "__main__":
    main()
