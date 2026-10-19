"""Relatório da auditoria ARP: texto de terceiros mascarado."""

from datetime import date, timedelta

import pytest

from pncp_ti.fontes.arp_auditoria import (
    _celula,
    caminho_do_motivo,
    no_universo,
    passariam_no_corte,
)
from pncp_ti.fontes.arp_regra import RegraArp

HOJE = date(2026, 10, 14)


def test_celula_mascara_cpf_e_escapa_barra_vertical():
    texto = _celula("TONER | fornecedor 12345678909")
    assert "12345678909" not in texto
    assert "|" not in texto


@pytest.mark.parametrize(
    ("vigente", "inicio", "fim", "esperado"),
    [
        (True, HOJE - timedelta(days=10), HOJE + timedelta(days=10), True),
        (True, None, HOJE, True),
        (True, HOJE + timedelta(days=1), HOJE + timedelta(days=90), False),  # começa amanhã
        (True, HOJE - timedelta(days=90), HOJE - timedelta(days=1), False),  # venceu ontem
        (False, HOJE - timedelta(days=10), HOJE + timedelta(days=10), False),  # cancelada
    ],
)
def test_universo_da_auditoria_e_o_mesmo_da_view(vigente, inicio, fim, esperado):
    ata = {"vigente_na_origem": vigente, "inicio": inicio, "fim": fim}
    assert no_universo(ata, HOJE) is esperado


def _id(compra: str, seq: int) -> str:
    return f"00000000000191-1-{compra}/2026-{seq:06d}"


def test_corte_aproximado_da_auditoria_usa_a_compra_e_os_itens_da_ata():
    """ADR 0025, item 7: o mesmo corte da carga, com a contagem de itens da listagem."""
    regra = RegraArp(0.5, frozenset({8435}), minimo_itens_ata=2)
    itens = {
        _id("000001", 1): {(239, "1")},  # mouse pad 1/1 numa compra de 10 itens
        _id("000002", 1): {(239, "1")},  # compra só de TI dividida entre dois fornecedores
        _id("000002", 2): {(283, "2")},
        _id("000003", 1): {(239, "1"), (283, "2")},  # 2 itens de TI numa compra genérica
        _id("000004", 1): {(8435, "1")},  # central
    }
    quantidades = {
        _id("000001", 1): 1,
        _id("000001", 2): 9,
        _id("000002", 1): 1,
        _id("000002", 2): 1,
        _id("000003", 1): 2,
        _id("000003", 2): 40,
        _id("000004", 1): 1,
        _id("000004", 2): 30,
    }
    assert passariam_no_corte(set(itens), itens, quantidades, regra) == {
        _id("000002", 1),
        _id("000002", 2),
        _id("000003", 1),
        _id("000004", 1),
    }


@pytest.mark.parametrize(
    ("motivo", "esperado"),
    [
        ("catmat70:pdm8435@item:central", "central"),
        ("catmat70:pdm239@item:compra3de6", "compra"),
        ("catmat70:pdm239@item:ata2itens", "ata"),
        ("catser1821:servico27502@item", "outro"),
        ("geral:informatica@objeto", "outro"),
        (None, "outro"),
    ],
)
def test_caminho_do_motivo(motivo, esperado):
    assert caminho_do_motivo(motivo) == esperado


async def test_auditoria_gera_relatorio_com_falso_negativo_e_nao_quebra(
    nome_banco_teste, conn_ingest, tmp_path, monkeypatch
):
    """Caminho inteiro (varredura, corte, relatório): o relatório com perdas é o que quebrava."""
    from dataclasses import replace
    from types import SimpleNamespace

    import arp_dados as d
    import psycopg
    from psycopg.rows import dict_row

    from pncp_ti.config import get_settings, ingest_dsn
    from pncp_ti.fontes import arp, arp_auditoria

    config = replace(get_settings(), arp_requests_per_second=1000.0, arp_max_requisicoes=5000)
    atas = [
        d.ata("70", "Insumos gerais"),  # central, mas a carga publicada não a avaliou
        d.ata("71", "Aquisição de notebooks"),
        d.ata("72", "Material diverso"),  # 1 de 6 itens de TI: incidental, avaliada pela carga
    ]
    atas[0]["quantidadeItens"] = 1
    atas[2]["quantidadeItens"] = 1  # a listagem erra a contagem: 1/1 pareceria uma perda
    itens = {
        d.id_ata("70"): [d.item("70", "1", "Notebook", pdm=8435, nome_pdm="PRODUTO CENTRAL")],
        d.id_ata("71"): [d.item("71", "1", "Notebook", nome_pdm="NOTEBOOK", pdm=None)],
        d.id_ata("72"): [
            d.item("72", "1", "Teclado", pdm=283),
            *(d.item("72", str(n), "Caneta", pdm=77) for n in range(2, 7)),
        ],
    }
    inicio = (d.hoje() - timedelta(days=30)).isoformat()

    def lote_de(*numeros):
        pdms = {"70": (8435, "PRODUTO CENTRAL"), "72": (283, "PRODUTO")}
        return [
            {
                **d.item(n, "1", "x", pdm=pdms[n][0], nome_pdm=pdms[n][1]),
                "dataVigenciaInicial": inicio,
            }
            for n in numeros
        ]

    # Carga publicada com varredura que só viu a ata 72: a 70 nunca foi avaliada (falso negativo)
    # e a 72 foi avaliada com os itens reais e é incidental (não é perda).
    publicada = d.ClienteFalso(atas, itens, pdms=[8435, 283])
    publicada.lote = lote_de("72")
    preparado, geracao = await arp.coletar(config, d.hoje(), client=publicada)
    await arp._publicar(conn_ingest, preparado, geracao, __import__("uuid").uuid4(), d.hoje())
    await conn_ingest.commit()
    assert not preparado.decisoes[d.id_ata("70")][0]
    assert preparado.decisoes[d.id_ata("72")][1] == "catalogo_incidental"

    com_varredura = d.ClienteFalso(atas, itens, pdms=[8435, 283])
    com_varredura.lote = lote_de("70", "72")

    class Contexto:
        async def __aenter__(self):
            return com_varredura

        async def __aexit__(self, *erro):
            return False

    async def conectar_teste(_):
        dsn = ingest_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
        return await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)

    monkeypatch.setattr(arp_auditoria, "get_settings", lambda: config)
    monkeypatch.setattr(arp_auditoria, "conectar", conectar_teste)
    monkeypatch.setattr(arp_auditoria, "DadosAbertosClient", lambda **kw: Contexto())
    monkeypatch.setattr(arp_auditoria, "RAIZ_EVALS", tmp_path)
    monkeypatch.setattr(
        arp_auditoria,
        "CacheVarredura",
        SimpleNamespace(do_ciclo=lambda hoje: arp.CacheVarredura.do_ciclo(hoje, tmp_path / "c")),
    )
    codigo = await arp_auditoria.principal()
    assert codigo == 0
    relatorio = next(tmp_path.glob("arp_*.md")).read_text(encoding="utf-8")
    assert "Recall medido pelo critério" in relatorio
    assert "PRODUTO CENTRAL" in relatorio  # a ata perdida lista o nome do PDM
    assert "incidentais**, item de TI sem passar no corte: 1" in relatorio
    assert "falsos negativos: **1**" in relatorio  # só a 70; a incidental 72 não é perda
    assert d.id_ata("72") not in relatorio.split("### Falsos negativos")[1].split("## Amostra")[0]
