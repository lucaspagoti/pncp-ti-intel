"""Consultas fixas e parametrizadas da web. Nenhum fragmento de SQL vem do usuário.

Ordenação e filtros chegam como valores de listas fechadas; o texto livre só entra como
parâmetro (`%(q)s`). Lê só views (papel `web_reader`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from pncp_ti.web import termos

TAMANHO_PAGINA = 20
LIMITE_EXPORTACAO = 5000
LIMITE_TEXTO = 200
ORDENS = {
    "relevancia": "rank DESC NULLS LAST, fim ASC, id_ata",
    "vencimento": "fim ASC, id_ata",
    "novas": "primeira_vez_vista DESC NULLS LAST, id_ata",
    "preco": "preco_min ASC NULLS LAST, id_ata",
}
ROTULOS_ORDEM = {
    "relevancia": "Relevância",
    "vencimento": "Vence primeiro",
    "novas": "Mais novas",
    "preco": "Menor preço",
}
FONTES = {"siga_rj": "SIGA RJ", "compras_arp": "Compras ARP", "pncp_busca": "PNCP"}
# Escopo da lista (ADR 0042): "PRODERJ" são as atas do SIGA gerenciadas pelo PRODERJ.
ESCOPOS = {"proderj": "PRODERJ"}
# `%%` porque a condição entra em consultas parametrizadas do psycopg.
PREDICADO_PRODERJ = "fonte = 'siga_rj' AND unidade_gerenciadora ILIKE 'PRODERJ%%'"
SEM_ESFERA = "Não informada"
ESFERAS = ("Federal", "Estadual", "Municipal", "Distrital", "Não se aplica", SEM_ESFERA)
DIAS_CRIT = 30
DIAS_WARN = 90
FUSO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    return datetime.now(FUSO).date()


def dias_restantes(fim: date | None, referencia: date | None = None) -> tuple[int | None, str]:
    """Dias até o fim da vigência e o nível do selo: `crit` até 30, `warn` até 90, senão ''."""
    if fim is None:
        return None, ""
    dias = (fim - (referencia or hoje())).days
    return dias, "crit" if dias <= DIAS_CRIT else "warn" if dias <= DIAS_WARN else ""


def como_texto(valor: Decimal | None) -> str:
    """Formato pt-BR sem milhar, para o link devolver o mesmo valor ao ser lido de novo."""
    return "" if valor is None else format(valor, "f").replace(".", ",")


@dataclass(frozen=True, slots=True)
class Filtros:
    q: str = ""
    escopo: str = ""
    fonte: str = ""
    esfera: str = ""
    uf: str = ""
    orgao: str = ""
    categoria: str = ""
    vigente_ate: date | None = None
    vence_ate: date | None = None
    desde: date | None = None
    preco_min: Decimal | None = None
    preco_max: Decimal | None = None
    ordem: str = "relevancia"
    pagina: int = 1

    def como_dict(self) -> dict[str, str]:
        """Só o que está preenchido, para refazer a URL (paginação, exportação)."""
        bruto = {
            "q": self.q,
            "escopo": self.escopo,
            "fonte": self.fonte,
            "esfera": self.esfera,
            "uf": self.uf,
            "orgao": self.orgao,
            "categoria": self.categoria,
            "vigente_ate": self.vigente_ate.isoformat() if self.vigente_ate else "",
            "vence_ate": self.vence_ate.isoformat() if self.vence_ate else "",
            "desde": self.desde.isoformat() if self.desde else "",
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
    escopo = params.get("escopo", "")
    fonte = params.get("fonte", "")
    esfera = params.get("esfera", "")
    uf = _texto(params.get("uf")).upper()
    categoria = params.get("categoria", "")
    ordem = params.get("ordem", "relevancia")
    try:
        pagina = max(1, min(int(params.get("pagina", "1")), 10_000))
    except ValueError:
        pagina = 1
    return Filtros(
        q=_texto(params.get("q")),
        escopo=escopo if escopo in ESCOPOS else "",
        fonte=fonte if fonte in FONTES else "",
        esfera=esfera if esfera in ESFERAS else "",
        uf=uf if len(uf) == 2 and uf.isalpha() else "",
        orgao=_texto(params.get("orgao")),
        categoria=categoria if termos.categoria(categoria) else "",
        vigente_ate=_data(params.get("vigente_ate")),
        vence_ate=_data(params.get("vence_ate")),
        desde=_data(params.get("desde")),
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


def alternativas(f: Filtros) -> list[str]:
    """O termo buscado e os sinônimos revisados dele (`insumos/sinonimos_busca.txt`).

    Sem termo, a categoria escolhida (`insumos/categorias_busca.txt`, ADR 0043) faz o papel da
    busca: seus termos são as alternativas. Com termo, a categoria só restringe (ver `_where`).
    """
    if f.q:
        return [f.q, *termos.sinonimos(f.q)]
    cat = termos.categoria(f.categoria)
    return list(cat.termos) if cat else []


def _tem_termo(f: Filtros) -> bool:
    """A busca por texto está ativa: um termo digitado ou uma categoria."""
    return bool(f.q or termos.categoria(f.categoria))


# Com termo, a busca junta os itens que casam (ADR 0036): pela cabeça (radical ou palavra exata) ou
# pelo texto inteiro com a palavra exata, que não pega `videomonitoramento` em "monitor". `n_exato`
# conta as cabeças com a palavra exata; `n_cabeca`, as que casam também pelo radical.
_CASAM = """
WITH alvo AS (SELECT {tsquery} AS tq, to_tsquery('simple', %(exato)s) AS te),
casam AS (
    SELECT i.fonte, i.id_ata,
           count(*) FILTER (WHERE i.cabeca_exata @@ alvo.te) AS n_exato,
           count(*) FILTER (WHERE i.cabeca_pt @@ alvo.tq OR i.cabeca_exata @@ alvo.te) AS n_cabeca,
           count(*) AS n_casam,
           min(i.valor_unitario) AS preco_min_casam,
           max(i.valor_unitario) AS preco_max_casam,
           array_agg(i.valor_unitario) FILTER (WHERE i.valor_unitario IS NOT NULL) AS precos_casam,
           (array_agg(i.cabeca_texto ORDER BY COALESCE(i.cabeca_exata @@ alvo.te, false) DESC,
                      i.cabeca_pt @@ alvo.tq DESC, i.valor_unitario NULLS LAST))[1] AS item_casado
    FROM v_busca_itens i, alvo
    WHERE i.cabeca_pt @@ alvo.tq OR COALESCE(i.cabeca_exata @@ alvo.te, false)
       OR COALESCE(i.texto_exato @@ alvo.te, false)
    GROUP BY i.fonte, i.id_ata
)
"""
_EXATO = "COALESCE(objeto_exato @@ te, false)"
# Foco no item: fatia dos itens da ata com a palavra exata na cabeça. Sem itens (busca PNCP), meio
# crédito quando o objeto traz a palavra exata.
_FOCO = (
    "CASE WHEN n_itens > 0 THEN COALESCE(n_exato, 0)::float8 / n_itens "
    f"WHEN {_EXATO} THEN 0.5 ELSE 0 END"
)
_NOTA = (
    f"2 * ({_FOCO}) + 0.5 * {_EXATO}::int + 0.25 * (COALESCE(n_cabeca, 0) > 0)::int "
    "+ 0.1 * (COALESCE(n_casam, 0) > 0)::int "
    "+ 0.05 * ts_rank_cd(documento_peso, tq, 1|32)"
)


def _origem(f: Filtros) -> tuple[str, str, dict[str, Any]]:
    """(CTE, FROM) da busca; sem termo nem categoria, só a view."""
    if not _tem_termo(f):
        return "", "v_busca_atas", {}
    alts = alternativas(f)
    p: dict[str, Any] = {f"q{n}": a for n, a in enumerate(alts)}
    p["exato"] = termos.consulta_exata(alts)
    tsquery = " || ".join(
        f"websearch_to_tsquery('portuguese', unaccent(%(q{n})s))" for n in range(len(alts))
    )
    cte = _CASAM.format(tsquery=f"({tsquery})")
    return cte, "v_busca_atas CROSS JOIN alvo LEFT JOIN casam USING (fonte, id_ata)", p


def _tsquery_categoria(n_termos: int, prefixo: str = "cat") -> str:
    """`websearch_to_tsquery` de cada termo da categoria, unidos por OU; só nomes de parâmetro."""
    return " || ".join(
        f"websearch_to_tsquery('portuguese', unaccent(%({prefixo}{n})s))" for n in range(n_termos)
    )


def _where(f: Filtros, sem: str = "") -> tuple[str, dict[str, Any]]:
    """WHERE dos filtros; `sem` deixa um campo de fora (contagem da faceta desse campo)."""
    cond = ["true"]
    p: dict[str, Any] = {}
    if _tem_termo(f):
        cond.append("documento @@ tq")
    cat = termos.categoria(f.categoria)
    if f.q and cat:
        # Termo dentro da categoria: o documento precisa casar com algum termo da categoria.
        for n, termo in enumerate(cat.termos):
            p[f"cat{n}"] = termo
        cond.append("documento @@ (" + _tsquery_categoria(len(cat.termos)) + ")")
    if f.escopo == "proderj" and sem != "escopo":
        cond.append(PREDICADO_PRODERJ)
    if f.fonte and sem != "fonte":
        cond.append("fonte = %(fonte)s")
        p["fonte"] = f.fonte
    if f.esfera == SEM_ESFERA and sem != "esfera":
        cond.append("esfera IS NULL")
    elif f.esfera and sem != "esfera":
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
    if f.vigente_ate:
        cond.append("fim >= %(vigente_ate)s")
        p["vigente_ate"] = f.vigente_ate
    if f.vence_ate:
        cond.append("fim <= %(vence_ate)s")
        p["vence_ate"] = f.vence_ate
    if f.desde:
        cond.append("primeira_vez_vista >= %(desde)s")
        p["desde"] = f.desde
    if f.preco_min is not None or f.preco_max is not None:
        # Um mesmo item precisa caber na faixa (mín. e máx. agregados deixariam passar uma ata
        # com itens de R$ 100 e R$ 1.000 numa faixa de R$ 200 a R$ 500). Com termo, vale o preço
        # dos itens que casam; só sem item que case vale o da ata toda.
        faixa = []
        if f.preco_min is not None:
            faixa.append("p >= %(preco_min)s")
            p["preco_min"] = f.preco_min
        if f.preco_max is not None:
            faixa.append("p <= %(preco_max)s")
            p["preco_max"] = f.preco_max
        # Item que casa sem preço válido não herda o preço de outro item da ata.
        precos = (
            "CASE WHEN n_casam > 0 THEN COALESCE(precos_casam, '{}') ELSE precos END"
            if _tem_termo(f)
            else "precos"
        )
        cond.append(f"EXISTS (SELECT 1 FROM unnest({precos}) AS p WHERE {' AND '.join(faixa)})")
    return " AND ".join(cond), p


def _consulta(f: Filtros, limite: int, deslocamento: int) -> tuple[str, dict[str, Any]]:
    cte, origem, p = _origem(f)
    onde, pw = _where(f)
    p.update(pw, limite=limite, deslocamento=deslocamento)
    if _tem_termo(f):
        extra = (
            f"{_NOTA} AS rank, n_casam, item_casado, "
            "CASE WHEN n_casam > 0 THEN preco_min_casam ELSE preco_min END AS preco_min_exibido, "
            "CASE WHEN n_casam > 0 THEN preco_max_casam ELSE preco_max END AS preco_max_exibido"
        )
        ordem = ORDENS[f.ordem].replace("preco_min ASC", "preco_min_exibido ASC")
    else:
        extra = (
            "0 AS rank, NULL::int AS n_casam, NULL::text AS item_casado, "
            "preco_min AS preco_min_exibido, preco_max AS preco_max_exibido"
        )
        ordem = ORDENS[f.ordem]
    return (
        f"{cte}SELECT {_COLUNAS}, {extra}, count(*) OVER () AS total "
        f"FROM {origem} WHERE {onde} ORDER BY {ordem} "
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


def janela_paginas(atual: int, total: int, vizinhas: int = 1) -> list[int | None]:
    """Números da paginação: a primeira, a última e as vizinhas da atual; `None` é reticências."""
    visiveis = {1, total, *range(max(1, atual - vizinhas), min(total, atual + vizinhas) + 1)}
    janela: list[int | None] = []
    anterior = 0
    for numero in sorted(visiveis):
        if numero - anterior == 2:
            janela.append(anterior + 1)  # uma lacuna de uma só página vale mais que "…"
        elif numero - anterior > 2:
            janela.append(None)
        janela.append(numero)
        anterior = numero
    return janela


async def total_atas(conn: psycopg.AsyncConnection) -> int:
    """Atas vigentes na base inteira, para a home."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT count(*) FROM v_busca_atas")
        return (await cur.fetchone())[0]


async def para_exportar(conn: psycopg.AsyncConnection, f: Filtros) -> list[dict[str, Any]]:
    sql, p = _consulta(f, LIMITE_EXPORTACAO, 0)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, p)
        return await cur.fetchall()


async def sugestoes(conn: psycopg.AsyncConnection, q: str) -> list[str]:
    """ "Você quis dizer": palavras parecidas nas cabeças dos itens (`pg_trgm`), até 3."""
    candidatas = [p for p in termos.palavras(q) if len(p) >= 4]
    if not candidatas:
        return []
    palavra = max(candidatas, key=len)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT palavra FROM v_busca_vocabulario WHERE palavra %% %(p)s AND palavra <> %(p)s "
            "ORDER BY similarity(palavra, %(p)s) DESC, n DESC LIMIT 3",
            {"p": palavra},
        )
        return [r["palavra"] for r in await cur.fetchall()]


async def opcoes_filtro(conn: psycopg.AsyncConnection) -> dict[str, list[str]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT DISTINCT uf FROM v_busca_atas WHERE uf IS NOT NULL ORDER BY 1")
        ufs = [r["uf"] for r in await cur.fetchall()]
    return {"ufs": ufs}


async def facetas(conn: psycopg.AsyncConnection, f: Filtros) -> dict[str, dict[str, int]]:
    """Contagem por fonte e por esfera sob os demais filtros; só opções com alguma ata."""
    resultado: dict[str, dict[str, int]] = {}
    for campo, expressao in (("fonte", "fonte"), ("esfera", f"COALESCE(esfera, '{SEM_ESFERA}')")):
        cte, origem, p = _origem(f)
        onde, pw = _where(f, sem=campo)
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"{cte}SELECT {expressao} AS valor, count(*) AS n FROM {origem} WHERE {onde} "
                "GROUP BY 1",
                {**p, **pw},
            )
            contagem = {r["valor"]: r["n"] for r in await cur.fetchall()}
        ordem = FONTES if campo == "fonte" else ESFERAS
        resultado[campo] = {v: contagem[v] for v in ordem if contagem.get(v)}
    # Abas "Todas | PRODERJ": as duas contagens sob os demais filtros, com o escopo de fora.
    cte, origem, p = _origem(f)
    onde, pw = _where(f, sem="escopo")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"{cte}SELECT count(*) AS todas, "
            f"count(*) FILTER (WHERE {PREDICADO_PRODERJ}) AS proderj "
            f"FROM {origem} WHERE {onde}",
            {**p, **pw},
        )
        linha = await cur.fetchone()
    resultado["escopo"] = {"": linha["todas"], "proderj": linha["proderj"]}
    return resultado


async def link_proderj(
    conn: psycopg.AsyncConnection, fonte: str, id_ata: str
) -> dict[str, str | None] | None:
    """`None` se a ata não é do PRODERJ; senão `{"url": ...}` (`url` nula: não consta no site)."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT url FROM v_ata_proderj WHERE fonte = %s AND id_ata = %s", (fonte, id_ata)
        )
        linha = await cur.fetchone()
    return None if linha is None else {"url": linha["url"]}


def filtros_ativos(f: Filtros) -> list[tuple[str, str, Filtros]]:
    """Pílulas: (rótulo, valor exibido, filtros sem esse campo) para o link de remover."""

    def sem(**campo: Any) -> Filtros:
        return replace(f, pagina=1, **campo)

    ativos: list[tuple[str, str, Filtros]] = []
    if f.q:
        ativos.append(("Termo", f.q, sem(q="")))
    if f.fonte:
        ativos.append(("Fonte", FONTES[f.fonte], sem(fonte="")))
    if f.esfera:
        ativos.append(("Esfera", f.esfera, sem(esfera="")))
    if f.uf:
        ativos.append(("UF", f.uf, sem(uf="")))
    if f.orgao:
        ativos.append(("Órgão", f.orgao, sem(orgao="")))
    if cat := termos.categoria(f.categoria):
        ativos.append(("Categoria", cat.rotulo, sem(categoria="")))
    if f.vigente_ate:
        ativos.append(
            ("Vigente até pelo menos", f.vigente_ate.strftime("%d/%m/%Y"), sem(vigente_ate=None))
        )
    if f.vence_ate:
        ativos.append(("Vence até", f.vence_ate.strftime("%d/%m/%Y"), sem(vence_ate=None)))
    if f.desde:
        ativos.append(("Novas desde", f.desde.strftime("%d/%m/%Y"), sem(desde=None)))
    if f.preco_min is not None:
        ativos.append(("Preço mín.", "R$ " + como_texto(f.preco_min), sem(preco_min=None)))
    if f.preco_max is not None:
        ativos.append(("Preço máx.", "R$ " + como_texto(f.preco_max), sem(preco_max=None)))
    return ativos


async def cargas(conn: psycopg.AsyncConnection) -> list[dict[str, Any]]:
    """Cargas ativas por fonte (rodapé "Dados de")."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT fonte, data_referencia, concluido_em FROM v_cargas_web ORDER BY fonte"
        )
        return await cur.fetchall()


async def ata(conn: psycopg.AsyncConnection, fonte: str, id_ata: str) -> dict[str, Any] | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_COLUNAS}, criterio_julgamento, licitacao, status_origem, processos, "
            "data_referencia FROM v_busca_atas WHERE fonte = %s AND id_ata = %s",
            (fonte, id_ata),
        )
        return await cur.fetchone()


async def itens(
    conn: psycopg.AsyncConnection, fonte: str, id_ata: str, limite: int | None = 2000
) -> list[dict[str, Any]]:
    """Itens da ata; a tela corta em 2.000, a exportação (`limite=None`) leva todos."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT id_item, descricao, nome_catalogo, codigo_catalogo, fornecedor, quantidade, "
            "valor_unitario, valor_valido, quantidade_empenhada, maximo_adesao FROM v_ata_itens_ti "
            "WHERE fonte = %s AND id_ata = %s ORDER BY id_item LIMIT %s",
            (fonte, id_ata, limite),
        )
        return await cur.fetchall()


DIAS_VENCENDO = 30
DIAS_NOVAS = 7


async def contagens_home(conn: psycopg.AsyncConnection) -> dict[str, Any]:
    """Números da home: total, recortes e uma contagem por categoria (ADR 0043).

    Uma consulta para os recortes e uma por categoria: `count(*) FILTER` com `@@` varre a view
    inteira (mais de 1 s); o `WHERE` usa o índice GIN do documento (cerca de 100 ms no todo).
    """
    cats = termos.categorias()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT count(*) AS todas, count(*) FILTER (WHERE fim <= %(vence)s) AS vencem, "
            "count(*) FILTER (WHERE primeira_vez_vista >= %(desde)s) AS novas, "
            f"count(*) FILTER (WHERE {PREDICADO_PRODERJ}) AS proderj, "
            "count(*) FILTER (WHERE uf = 'RJ') AS rj FROM v_busca_atas",
            {
                "vence": hoje() + timedelta(days=DIAS_VENCENDO),
                "desde": hoje() - timedelta(days=DIAS_NOVAS),
            },
        )
        linha = await cur.fetchone()
        contagem: list[tuple[termos.Categoria, int]] = []
        for cat in cats:
            await cur.execute(
                "SELECT count(*) AS n FROM v_busca_atas WHERE documento @@ ("
                + _tsquery_categoria(len(cat.termos))
                + ")",
                {f"cat{n}": termo for n, termo in enumerate(cat.termos)},
            )
            contagem.append((cat, (await cur.fetchone())["n"]))
    return {"total": linha["todas"], "categorias": contagem, "recortes": recortes(linha)}


def recortes(linha: Mapping[str, int]) -> list[dict[str, Any]]:
    """Faixa da home: rótulo, endereço e contagem. Vencimento em alerta (`--warn`)."""
    h = hoje()
    return [
        {
            "rotulo": "Vencem em 30 dias",
            "url": "/?"
            + urlencode(
                {
                    "vence_ate": (h + timedelta(days=DIAS_VENCENDO)).isoformat(),
                    "ordem": "vencimento",
                }
            ),
            "n": linha["vencem"],
            "alerta": True,
        },
        {
            "rotulo": "Entraram nesta semana",
            "url": "/?"
            + urlencode({"desde": (h - timedelta(days=DIAS_NOVAS)).isoformat(), "ordem": "novas"}),
            "n": linha["novas"],
            "alerta": False,
        },
        {"rotulo": "PRODERJ", "url": "/?escopo=proderj", "n": linha["proderj"], "alerta": False},
        {"rotulo": "Rio de Janeiro", "url": "/?uf=RJ", "n": linha["rj"], "alerta": False},
        {"rotulo": "Todas as atas", "url": "/?explorar=1", "n": linha["todas"], "alerta": False},
    ]
