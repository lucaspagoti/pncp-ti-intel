"""Relatório da auditoria ARP: texto de terceiros mascarado."""

from datetime import date, timedelta

import pytest

from pncp_ti.fontes.arp_auditoria import _celula, no_universo

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
    atas = [d.ata("70", "Insumos gerais"), d.ata("71", "Aquisição de notebooks")]
    atas[0]["quantidadeItens"] = 1
    itens = {
        d.id_ata("70"): [d.item("70", "1", "Notebook", pdm=8435, nome_pdm="PRODUTO CENTRAL")],
        d.id_ata("71"): [d.item("71", "1", "Notebook", nome_pdm="NOTEBOOK", pdm=None)],
    }
    inicio = (d.hoje() - timedelta(days=30)).isoformat()
    lote = [
        {
            **d.item("70", "1", "Notebook", pdm=8435, nome_pdm="PRODUTO CENTRAL"),
            "dataVigenciaInicial": inicio,
        }
    ]

    # Carga publicada SEM varredura: a ata 70 (objeto genérico) fica de fora, é falso negativo.
    sem_varredura = d.ClienteFalso(atas, itens, pdms=[8435])
    preparado, geracao = await arp.coletar(config, d.hoje(), client=sem_varredura)
    await arp._publicar(conn_ingest, preparado, geracao, __import__("uuid").uuid4(), d.hoje())
    await conn_ingest.commit()
    assert not preparado.decisoes[d.id_ata("70")][0]  # sem varredura, objeto genérico fica fora

    com_varredura = d.ClienteFalso(atas, itens, pdms=[8435])
    com_varredura.lote = lote

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
