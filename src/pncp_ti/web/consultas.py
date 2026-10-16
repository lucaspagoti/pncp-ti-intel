"""Consultas fixas e parametrizadas da web. Nenhum fragmento de SQL vem do usuário.

Ordenação e filtros chegam como valores de listas fechadas; o texto livre só entra como
parâmetro (`%(q)s`). Lê só views (papel `web_reader`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
from psycopg.rows import dict_row

TAMANHO_PAGINA = 25
LIMITE_EXPORTACAO = 5000
LIMITE_TEXTO = 200
ORDENS = {
    "relevancia": "rank DESC NULLS LAST, fim ASC, id_ata",
    "vencimento": "fim ASC, id_ata",
    "novas": "primeira_vez_vista DESC NULLS LAST, id_ata",
    "preco": "preco_min ASC NULLS LAST, id_ata",
}
FONTES = {"siga_rj": "SIGA RJ", "compras_arp": "Compras.gov.br", "pncp_busca": "Busca PNCP"}
ESFERAS = ("Federal", "Estadual", "Municipal", "Distrital")


def como_texto(valor: Decimal | None) -> str:
    """Formato pt-BR sem milhar, para o link devolver o mesmo valor ao ser lido de novo."""
    return "" if valor is None else format(valor, "f").replace(".", ",")


@dataclass(frozen=True, slots=True)
class Filtros:
    q: str = ""
    fonte: str = ""
    esfera: str = ""
    uf: str = ""
    orgao: str = ""
    vence_ate: date | None = None
    preco_min: Decimal | None = None
    preco_max: Decimal | None = None
    ordem: str = "relevancia"
    pagina: int = 1

    def como_dict(self) -> dict[str, str]:
        """Só o que está preenchido, para refazer a URL (paginação, exportação)."""
        bruto = {
            "q": self.q,
            "fonte": self.fonte,
            "esfera": self.esfera,
            "uf": self.uf,
            "orgao": self.orgao,
            "vence_ate": self.vence_ate.isoformat() if self.vence_ate else "",
            "preco_min": como_texto(self.preco_min),
            "preco_max": como_texto(self.preco_max),
            "ordem": self.ordem if self.ordem != "relevancia" else "",
        }
        return {k: v for k, v in bruto.items() if v}


def _texto(valor: str | None) -> str:
    return " ".join((valor or "").split())[:LIMITE_TEXTO]


def _data(valor: str | None) -> date | None:
    try:
        return date.fromisoformat((valor or "").strip()) if valor else None
    except ValueError:
        return None


def _preco(valor: str | None) -> Decimal | None:
    """Aceita `1.234,50` (pt-BR), `1234,50` e `12.50` (ponto com 1–2 casas é decimal)."""
    if not valor:
        return None
    texto = valor.strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif texto.count(".") == 1 and len(texto.rsplit(".", 1)[1]) != 3:
        pass  # ponto decimal
    else:
        texto = texto.replace(".", "")  # `1.000` ou `1.234.567`: separador de milhar
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    return numero if numero.is_finite() and 0 <= numero < Decimal("1e12") else None


def ler_filtros(params: Mapping[str, str]) -> Filtros:
    """Normaliza a query string; valor fora da lista fechada vira vazio."""
    fonte = params.get("fonte", "")
    esfera = params.get("esfera", "")
    uf = _texto(params.get("uf")).upper()
    ordem = params.get("ordem", "relevancia")
    try:
        pagina = max(1, min(int(params.get("pagina", "1")), 10_000))
    except ValueError:
        pagina = 1
    return Filtros(
        q=_texto(params.get("q")),
        fonte=fonte if fonte in FONTES else "",
        esfera=esfera if esfera in ESFERAS else "",
        uf=uf if len(uf) == 2 and uf.isalpha() else "",
        orgao=_texto(params.get("orgao")),
        vence_ate=_data(params.get("vence_ate")),
        preco_min=_preco(params.get("preco_min")),
        preco_max=_preco(params.get("preco_max")),
        ordem=ordem if ordem in ORDENS else "relevancia",
        pagina=pagina,
    )


_COLUNAS = (
    "fonte, id_ata, numero, orgao, unidade_gerenciadora, objeto, inicio, fim, esfera, uf, "
    "municipio, link_origem, valor_total, n_itens, preco_min, preco_max, primeira_vez_vista, "
    "motivo_ti, numero_controle_pncp"
)


def _where(f: Filtros) -> tuple[str, dict[str, Any]]:
    cond = ["true"]
    p: dict[str, Any] = {}
    if f.q:
        p["q"] = f.q
        cond.append(
            "to_tsvector('portuguese', texto_busca) @@ websearch_to_tsquery('portuguese', "
            "unaccent(%(q)s))"
        )
    if f.fonte:
        cond.append("fonte = %(fonte)s")
        p["fonte"] = f.fonte
    if f.esfera:
        cond.append("esfera = %(esfera)s")
        p["esfera"] = f.esfera
    if f.uf:
        cond.append("uf = %(uf)s")
        p["uf"] = f.uf
    if f.orgao:
        cond.append(
            "unaccent(lower(concat_ws(' ', orgao, unidade_gerenciadora))) "
            "LIKE '%%' || unaccent(lower(%(orgao)s)) || '%%'"
        )
        p["orgao"] = f.orgao.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    if f.vence_ate:
        cond.append("fim <= %(vence_ate)s")
        p["vence_ate"] = f.vence_ate
    if f.preco_min is not None or f.preco_max is not None:
        # Um mesmo item precisa caber na faixa (mín. e máx. agregados deixariam passar uma ata
        # com itens de R$ 100 e R$ 1.000 numa faixa de R$ 200 a R$ 500).
        faixa = []
        if f.preco_min is not None:
            faixa.append("p >= %(preco_min)s")
            p["preco_min"] = f.preco_min
        if f.preco_max is not None:
            faixa.append("p <= %(preco_max)s")
            p["preco_max"] = f.preco_max
        cond.append(f"EXISTS (SELECT 1 FROM unnest(precos) AS p WHERE {' AND '.join(faixa)})")
    return " AND ".join(cond), p


def _consulta(f: Filtros, limite: int, deslocamento: int) -> tuple[str, dict[str, Any]]:
    onde, p = _where(f)
    rank = (
        "ts_rank(to_tsvector('portuguese', texto_busca), "
        "websearch_to_tsquery('portuguese', unaccent(%(q)s)))"
        if f.q
        else "0"
    )
    p.update(limite=limite, deslocamento=deslocamento)
    return (
        f"SELECT {_COLUNAS}, {rank} AS rank, count(*) OVER () AS total "
        f"FROM v_busca_atas WHERE {onde} ORDER BY {ORDENS[f.ordem]} "
        "LIMIT %(limite)s OFFSET %(deslocamento)s",
        p,
    )


@dataclass(frozen=True, slots=True)
class Pagina:
    linhas: list[dict[str, Any]]
    total: int
    pagina: int
    paginas: int


async def buscar(conn: psycopg.AsyncConnection, f: Filtros) -> Pagina:
    sql, p = _consulta(f, TAMANHO_PAGINA, (f.pagina - 1) * TAMANHO_PAGINA)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, p)
        linhas = await cur.fetchall()
    total = linhas[0]["total"] if linhas else 0
    return Pagina(linhas, total, f.pagina, max(1, -(-total // TAMANHO_PAGINA)))


async def para_exportar(conn: psycopg.AsyncConnection, f: Filtros) -> list[dict[str, Any]]:
    sql, p = _consulta(f, LIMITE_EXPORTACAO, 0)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, p)
        return await cur.fetchall()


async def opcoes_filtro(conn: psycopg.AsyncConnection) -> dict[str, list[str]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT DISTINCT uf FROM v_atas_ti_vigentes WHERE uf IS NOT NULL ORDER BY 1"
        )
        ufs = [r["uf"] for r in await cur.fetchall()]
    return {"ufs": ufs}


async def ata(conn: psycopg.AsyncConnection, fonte: str, id_ata: str) -> dict[str, Any] | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_COLUNAS}, criterio_julgamento, licitacao, status_origem, processos, "
            "data_referencia FROM v_busca_atas WHERE fonte = %s AND id_ata = %s",
            (fonte, id_ata),
        )
        return await cur.fetchone()


async def itens(conn: psycopg.AsyncConnection, fonte: str, id_ata: str) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT id_item, descricao, nome_catalogo, fornecedor, quantidade, valor_unitario, "
            "valor_valido, quantidade_empenhada, maximo_adesao FROM v_ata_itens_ti "
            "WHERE fonte = %s AND id_ata = %s ORDER BY id_item LIMIT 2000",
            (fonte, id_ata),
        )
        return await cur.fetchall()


async def consumo(conn: psycopg.AsyncConnection, fonte: str, id_ata: str) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT id_item, item, unidade_participante, qtd_demandada, qtd_consumida "
            "FROM v_ata_consumo_item WHERE fonte = %s AND id_ata = %s "
            "ORDER BY id_item, unidade_participante LIMIT 2000",
            (fonte, id_ata),
        )
        return await cur.fetchall()
