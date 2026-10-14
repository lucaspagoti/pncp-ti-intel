"""Carga diária do SIGA RJ: download, validação, classificação e troca atômica (ADR 0019).

Fluxo: baixa os 3 CSVs (sha256, Last-Modified) → valida e normaliza (`siga_csv`) →
classifica TI (`classificar.in05`) → grava numa carga nova e troca a ativa dentro de
uma única transação. Falha em qualquer etapa deixa a carga anterior visível.

    python -m pncp_ti.fontes.siga                    # baixa e carrega
    python -m pncp_ti.fontes.siga --validar          # baixa e valida, sem gravar
    python -m pncp_ti.fontes.siga --de-diretorio D   # reprocessa arquivos locais
    python -m pncp_ti.fontes.siga --forcar           # republica mesmo sem mudança nos arquivos
                                                     # (reclassifica após mudar a regra de TI)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import psycopg
import structlog

from pncp_ti.classificar.in05 import classificar_ata, versao_regra
from pncp_ti.config import get_settings
from pncp_ti.db import conectar
from pncp_ti.fontes.siga_csv import ConjuntoSiga, ErroValidacao, montar

FONTE = "siga_rj"
URL_BASE = "https://www.compras.rj.gov.br/siga/imagens/"
ARQUIVOS = {
    "atas": "ATA_REGISTRO_PRECO.CSV",
    "itens": "ITENS_ATAS_REGISTRO_PRECO.CSV",
    "participantes": "PARTICIPANTES_ATAS_REGISTRO_PRECO.CSV",
}
LIMITE_BYTES = 100 * 1024 * 1024  # o maior arquivo real tem ~50 MB; a leitura usa ~9x em RAM
JANELA_GERACAO = timedelta(minutes=15)
PISO_RELATIVO = 0.5
PISO_FILHOS = 0.7  # itens e participantes: arquivo regenerado pela metade não pode publicar
DEFASAGEM_ALERTA_DIAS = 3
CHAVE_TRAVA = "carga:siga_rj"
# Formato atual (timestamp-sufixo) e o anterior (só timestamp): ambos contêm CSV bruto a podar.
_PASTA_CARGA = re.compile(r"^\d{8}T\d{6}(-[0-9a-f]{8})?$")
RETER_CARGAS = 3
TENTATIVAS = 3
RAIZ_DADOS = Path(__file__).resolve().parents[3] / "data" / "siga"

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class ArquivoBaixado:
    caminho: Path
    sha256: str
    tamanho: int
    last_modified: datetime | None


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    carga_id: UUID
    status: str  # concluida | sem_mudanca
    contagens: dict[str, int]


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


class _Transitorio(Exception):
    pass


async def _baixar_um(client: httpx.AsyncClient, nome: str, destino: Path) -> ArquivoBaixado:
    url = URL_BASE + ARQUIVOS[nome]
    parcial = destino.with_suffix(destino.suffix + ".part")
    ultimo: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resumo = hashlib.sha256()
            tamanho = 0
            async with client.stream("GET", url) as resposta:
                if resposta.status_code >= 500:
                    raise _Transitorio(f"HTTP {resposta.status_code}")
                if resposta.status_code != 200:
                    raise ErroValidacao("http", f"{ARQUIVOS[nome]}: HTTP {resposta.status_code}")
                esperado = resposta.headers.get("content-length")
                if esperado is not None and not esperado.isdigit():
                    raise ErroValidacao("http", f"{ARQUIVOS[nome]}: Content-Length inválido")
                if esperado and int(esperado) > LIMITE_BYTES:
                    raise ErroValidacao("tamanho", f"{ARQUIVOS[nome]}: {esperado} bytes")
                with parcial.open("wb") as saida:
                    async for bloco in resposta.aiter_bytes(1 << 16):
                        tamanho += len(bloco)
                        if tamanho > LIMITE_BYTES:
                            raise ErroValidacao("tamanho", f"{ARQUIVOS[nome]}: acima do limite")
                        resumo.update(bloco)
                        saida.write(bloco)
                if esperado and int(esperado) != tamanho:
                    raise _Transitorio(f"truncado: {tamanho} de {esperado} bytes")
                modificado = resposta.headers.get("last-modified")
            parcial.replace(destino)
            destino.chmod(0o600)  # o CSV bruto tem CPF completo (ADR 0019)
            return ArquivoBaixado(
                caminho=destino,
                sha256=resumo.hexdigest(),
                tamanho=tamanho,
                last_modified=parsedate_to_datetime(modificado) if modificado else None,
            )
        except (_Transitorio, httpx.TransportError) as exc:
            ultimo = exc
            parcial.unlink(missing_ok=True)
            log.warning(
                "siga_download_retry", arquivo=nome, tentativa=tentativa, erro=str(exc)[:120]
            )
            if tentativa < TENTATIVAS:
                await asyncio.sleep(2.0 * tentativa)
        except BaseException:
            parcial.unlink(missing_ok=True)
            raise
    raise ErroValidacao("rede", f"{ARQUIVOS[nome]}: falhou após {TENTATIVAS} tentativas: {ultimo}")


async def baixar(
    destino: Path, client: httpx.AsyncClient | None = None
) -> dict[str, ArquivoBaixado]:
    destino.mkdir(parents=True, exist_ok=False, mode=0o700)  # exclusivo por execução
    proprio = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, read=180.0),
            headers={
                "User-Agent": "pncp-ti-intel/0.1 (pesquisa pessoal)",
                "Accept-Encoding": "identity",
            },
            follow_redirects=False,
        )
    try:
        baixados = {
            nome: await _baixar_um(client, nome, destino / ARQUIVOS[nome]) for nome in ARQUIVOS
        }
    finally:
        if proprio:
            await client.aclose()
    modificados = [a.last_modified for a in baixados.values() if a.last_modified]
    if len(modificados) == len(baixados) and max(modificados) - min(modificados) > JANELA_GERACAO:
        raise ErroValidacao(
            "geracao", f"Last-Modified dos 3 arquivos difere em mais de {JANELA_GERACAO}"
        )
    return baixados


def arquivos_de_diretorio(diretorio: Path) -> dict[str, ArquivoBaixado]:
    resultado = {}
    for nome, arquivo in ARQUIVOS.items():
        caminho = diretorio / arquivo
        if not caminho.is_file():
            raise ErroValidacao("arquivo", f"{caminho} não existe")
        resultado[nome] = ArquivoBaixado(
            caminho=caminho,
            sha256=_sha256(caminho),
            tamanho=caminho.stat().st_size,
            last_modified=None,
        )
    return resultado


def _geracao(arquivos: Mapping[str, ArquivoBaixado]) -> dict[str, dict[str, object]]:
    geracao: dict[str, dict[str, object]] = {
        nome: {
            "arquivo": ARQUIVOS[nome],
            "sha256": a.sha256,
            "bytes": a.tamanho,
            "last_modified": a.last_modified.astimezone(UTC).isoformat()
            if a.last_modified
            else None,
        }
        for nome, a in arquivos.items()
    }
    geracao["_regra"] = {"versao": versao_regra()}
    return geracao


def preparar(
    arquivos: Mapping[str, ArquivoBaixado],
) -> tuple[ConjuntoSiga, dict[str, tuple[bool, str]]]:
    """Valida e classifica; sem banco. Devolve o conjunto e `{id_ata: (is_ti, motivo)}`."""
    conjunto = montar(
        arquivos["atas"].caminho.read_bytes(),
        arquivos["itens"].caminho.read_bytes(),
        arquivos["participantes"].caminho.read_bytes(),
    )
    nomes: dict[str, set[str]] = {}
    for item in conjunto.itens:
        nomes.setdefault(item.ata_id_origem, set()).add(item.nome_catalogo)
    decisoes = {}
    for ata in conjunto.atas:
        decisao = classificar_ata(ata.objeto, sorted(nomes.get(ata.id_origem, ())))
        decisoes[ata.id_origem] = (decisao.is_ti, decisao.motivo)
    conjunto.contagens["atas_ti"] = sum(1 for ti, _ in decisoes.values() if ti)
    conjunto.contagens["atas_validas_ti"] = sum(
        1 for a in conjunto.atas if a.status_origem == "Válida" and decisoes[a.id_origem][0]
    )
    return conjunto, decisoes


async def _copiar(conn: psycopg.AsyncConnection, comando: str, linhas) -> None:
    async with conn.cursor() as cur, cur.copy(comando) as copia:
        for linha in linhas:
            await copia.write_row(linha)


async def _publicar(
    conn: psycopg.AsyncConnection,
    conjunto: ConjuntoSiga,
    decisoes: Mapping[str, tuple[bool, str]],
    geracao: dict[str, dict[str, object]],
    carga_id: UUID,
    forcar: bool = False,
) -> ResultadoCarga:
    async with conn.transaction():
        bloqueio = await (
            await conn.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS ok", (CHAVE_TRAVA,)
            )
        ).fetchone()
        if not bloqueio["ok"]:
            raise ErroValidacao("concorrente", "outra carga do SIGA RJ está em andamento")

        ativa = await (
            await conn.execute(
                "SELECT id, geracao, contagens, data_referencia FROM cargas "
                "WHERE fonte = %s AND ativa",
                (FONTE,),
            )
        ).fetchone()

        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        if conjunto.data_extracao > hoje + timedelta(days=1):
            raise ErroValidacao(
                "geracao_futura", f"data_extracao {conjunto.data_extracao} está no futuro"
            )

        # Sem mudança = mesmos 3 arquivos E mesma regra de TI; mudar a regra reclassifica sozinho.
        mesma_geracao = (
            ativa is not None
            and ativa["geracao"].get("_regra") == geracao["_regra"]
            and all(
                ativa["geracao"].get(n, {}).get("sha256") == geracao[n]["sha256"] for n in ARQUIVOS
            )
        )
        if ativa and not forcar and mesma_geracao:
            defasagem = (hoje - conjunto.data_extracao).days
            if defasagem > DEFASAGEM_ALERTA_DIAS:
                log.warning("siga_arquivo_defasado", dias=defasagem)
            await conn.execute(
                "INSERT INTO cargas (id, fonte, data_referencia, status, concluido_em, geracao, "
                "contagens) VALUES (%s, %s, %s, 'sem_mudanca', now(), %s, %s)",
                (
                    carga_id,
                    FONTE,
                    conjunto.data_extracao,
                    json.dumps(geracao),
                    json.dumps({"defasagem_dias": defasagem}),
                ),
            )
            return ResultadoCarga(carga_id, "sem_mudanca", ativa["contagens"])

        if ativa:
            if conjunto.data_extracao < ativa["data_referencia"]:
                raise ErroValidacao(
                    "geracao_antiga",
                    f"data_extracao {conjunto.data_extracao} anterior à carga ativa "
                    f"({ativa['data_referencia']})",
                )
            for chave, atual, piso in (
                ("atas_unicas", len(conjunto.atas), PISO_RELATIVO),
                ("itens_gravados", len(conjunto.itens), PISO_FILHOS),
                ("participantes_gravados", len(conjunto.participantes), PISO_FILHOS),
            ):
                anteriores = int(ativa["contagens"].get(chave, 0))
                if anteriores and atual < piso * anteriores:
                    raise ErroValidacao(
                        "queda_volume", f"{chave}: {atual} contra {anteriores} na carga ativa"
                    )

        await conn.execute(
            "INSERT INTO cargas (id, fonte, data_referencia, status, geracao) "
            "VALUES (%s, %s, %s, 'em_andamento', %s)",
            (carga_id, FONTE, conjunto.data_extracao, json.dumps(geracao)),
        )
        await _copiar(
            conn,
            "COPY atas (carga_id, id_origem, numero, unidade_gerenciadora, objeto, licitacao, "
            "inicio, fim, criterio_julgamento, status_origem, processos, is_ti, motivo_ti, "
            "vigente_na_origem) FROM STDIN",
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
                    a.criterio_julgamento,
                    a.status_origem,
                    list(a.processos),
                    *decisoes[a.id_origem],
                    a.status_origem == "Válida",
                )
                for a in conjunto.atas
            ),
        )
        await _copiar(
            conn,
            "COPY ata_itens (carga_id, chave, ata_id_origem, id_item, descricao, nome_catalogo, "
            "id_fornecedor, fornecedor, quantidade, valor_unitario, taxa_pct, valor_valido) "
            "FROM STDIN",
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
                    i.taxa_pct,
                    i.valor_valido,
                )
                for i in conjunto.itens
            ),
        )
        await _copiar(
            conn,
            "COPY ata_participantes (carga_id, chave, ata_id_origem, id_item, item, unidade, "
            "qtd_demandada, qtd_consumida, valor_demandado, valor_consumido) FROM STDIN",
            (
                (
                    carga_id,
                    p.chave,
                    p.ata_id_origem,
                    p.id_item,
                    p.item,
                    p.unidade,
                    p.qtd_demandada,
                    p.qtd_consumida,
                    p.valor_demandado,
                    p.valor_consumido,
                )
                for p in conjunto.participantes
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
            (json.dumps(conjunto.contagens), carga_id),
        )
        await conn.execute(
            "INSERT INTO atas_vistas (fonte, id_origem, primeira_vez_vista) "
            "SELECT %s, id_origem, (now() AT TIME ZONE 'America/Sao_Paulo')::date "
            "FROM atas WHERE carga_id = %s ON CONFLICT DO NOTHING",
            (FONTE, carga_id),
        )
    return ResultadoCarga(carga_id, "concluida", conjunto.contagens)


async def _registrar_falha(
    conn: psycopg.AsyncConnection,
    carga_id: UUID,
    exc: BaseException,
    geracao: dict[str, dict[str, object]],
    fonte: str = FONTE,
) -> None:
    # Só tipo e mensagem curta. Exceção do driver pode trazer "Failing row contains (...)",
    # então fora de ErroValidacao grava apenas a classe e o SQLSTATE.
    if isinstance(exc, ErroValidacao):
        tipo, mensagem = exc.tipo, str(exc)
    else:
        tipo = type(exc).__name__
        mensagem = f"{tipo} sqlstate={getattr(exc, 'sqlstate', None)}"
    await conn.rollback()
    await conn.execute(
        "INSERT INTO cargas (id, fonte, data_referencia, status, concluido_em, geracao, "
        "erro_tipo, erro_mensagem) VALUES (%s, %s, (now() AT TIME ZONE "
        "'America/Sao_Paulo')::date, 'falhou', now(), %s, %s, %s)",
        (carga_id, fonte, json.dumps(geracao), tipo, mensagem[:500]),
    )
    await conn.commit()


async def carregar(
    conn: psycopg.AsyncConnection, arquivos: Mapping[str, ArquivoBaixado], *, forcar: bool = False
) -> ResultadoCarga:
    carga_id = uuid4()
    geracao = _geracao(arquivos)
    try:
        conjunto, decisoes = preparar(arquivos)
        return await _publicar(conn, conjunto, decisoes, geracao, carga_id, forcar)
    except Exception as exc:
        await _registrar_falha(conn, carga_id, exc, geracao)
        raise


def _reter_ultimas(raiz: Path, manter: int = RETER_CARGAS) -> None:
    if not raiz.is_dir():
        return
    pastas = sorted(
        (p for p in raiz.iterdir() if p.is_dir() and _PASTA_CARGA.match(p.name)),
        key=lambda p: p.name,
    )
    for pasta in pastas[:-manter] if manter else pastas:
        shutil.rmtree(pasta, ignore_errors=True)


async def tentar_trava_sessao(conn: psycopg.AsyncConnection, chave: str = CHAVE_TRAVA) -> bool:
    """Trava de sessão que cobre download + parse + publicação (a de transação só cobre o fim).

    Dura até a conexão fechar; sobrevive a commit/rollback.
    """
    linha = await (
        await conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS ok", (chave,))
    ).fetchone()
    await conn.commit()
    return bool(linha["ok"])


async def _conectar_com_trava() -> psycopg.AsyncConnection:
    conn = await conectar(get_settings())
    if not await tentar_trava_sessao(conn):
        await conn.close()
        raise ErroValidacao("concorrente", "outra execução do SIGA RJ já está em andamento")
    return conn


async def baixar_registrando(
    conn: psycopg.AsyncConnection, destino: Path, client: httpx.AsyncClient | None = None
) -> dict[str, ArquivoBaixado]:
    """Baixa e, se falhar, deixa a falha em `cargas` (distingue "fonte caída" de "sem novidade")."""
    try:
        return await baixar(destino, client)
    except Exception as exc:
        await _registrar_falha(conn, uuid4(), exc, {})
        raise


async def principal(argumentos: argparse.Namespace) -> int:
    conn: psycopg.AsyncConnection | None = None
    baixou = False
    try:
        if argumentos.de_diretorio:
            arquivos = arquivos_de_diretorio(argumentos.de_diretorio)
        else:
            RAIZ_DADOS.mkdir(parents=True, exist_ok=True)
            RAIZ_DADOS.chmod(0o700)
            # Diretório exclusivo: timestamp + sufixo aleatório (duas execuções no mesmo segundo
            # não compartilham pasta nem arquivos .part).
            destino = RAIZ_DADOS / (
                f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
            )
            baixou = True
            if argumentos.validar:
                arquivos = await baixar(destino)
            else:
                conn = await _conectar_com_trava()
                arquivos = await baixar_registrando(conn, destino)
            destino.chmod(0o700)
        if argumentos.validar:
            conjunto, _ = preparar(arquivos)
            log.info(
                "siga_validado", data_extracao=str(conjunto.data_extracao), **conjunto.contagens
            )
            return 0
        if conn is None:
            conn = await _conectar_com_trava()
        resultado = await carregar(conn, arquivos, forcar=argumentos.forcar)
        log.info(
            "siga_carga",
            carga_id=str(resultado.carga_id),
            status=resultado.status,
            **resultado.contagens,
        )
        return 0
    except ErroValidacao as exc:
        log.error("siga_falha", tipo=exc.tipo, mensagem=str(exc))
        return 1
    except Exception as exc:
        # Sem traceback: exceções do driver podem carregar linhas dos arquivos.
        log.error("siga_falha", tipo=type(exc).__name__, sqlstate=getattr(exc, "sqlstate", None))
        return 1
    finally:
        if conn is not None:
            await conn.close()
        if baixou:
            _reter_ultimas(RAIZ_DADOS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga do SIGA RJ (atas, itens, participantes).")
    parser.add_argument("--de-diretorio", type=Path, help="reprocessa os 3 CSVs de uma pasta")
    parser.add_argument("--validar", action="store_true", help="valida sem gravar no banco")
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="republica mesmo com os mesmos arquivos (reclassificar)",
    )
    raise SystemExit(asyncio.run(principal(parser.parse_args())))


if __name__ == "__main__":
    main()
