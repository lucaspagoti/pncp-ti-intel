"""Cobertura da busca PNCP contra o ARP (R3, D6): contas, causas das perdas e relatório."""

from datetime import date, timedelta

import pytest

from pncp_ti.fontes.pncp_busca_auditoria import (
    avaliar,
    base_do_motivo,
    relatorio,
    termos_da_busca,
    versao_termos,
)

HOJE = date(2026, 10, 17)


def _controle(n: int) -> str:
    return f"00394452000103-1-{n:06d}/2025-000001"


def _link(n: int) -> str:
    return f"https://pncp.gov.br/app/atas/00394452000103/2025/{n}/1"


def _vigencia(fim=HOJE + timedelta(days=30), vigente=True):
    return {"inicio": HOJE - timedelta(days=30), "fim": fim, "vigente_na_origem": vigente}


def _arp(n, objeto, motivo, *, ti=True, **vigencia):
    return {
        "numero_controle_pncp": _controle(n),
        "objeto": objeto,
        "motivo_ti": motivo,
        "is_ti": ti,
        "link_origem": _link(n),
        "esfera": None,
        "uf": None,
        **_vigencia(**vigencia),
    }


def _busca(n, objeto, termos, **vigencia):
    return {
        "numero_controle_pncp": _controle(n),
        "objeto": objeto,
        "motivo_ti": "termo_pncp:" + "|".join(termos),
        "link_origem": _link(n),
        "esfera": "Municipal",
        "uf": "RJ",
        **_vigencia(**vigencia),
    }


@pytest.mark.parametrize(
    ("motivo", "base"),
    [
        ("catmat70:pdm8435@item:central", "catalogo"),
        ("catser1821:x@item:prop1de2", "catalogo"),
        ("III-computadores:impressora@item", "item"),
        ("geral:informatica@objeto", "objeto"),
    ],
)
def test_base_do_motivo_separa_catalogo_item_e_objeto(motivo, base):
    assert base_do_motivo(motivo) == base


def test_termos_e_versao_da_lista():
    assert termos_da_busca("termo_pncp:notebook|toner") == ["notebook", "toner"]
    assert termos_da_busca("geral:informatica@objeto") == []
    assert versao_termos(["a", "b"]) != versao_termos(["a"])
    assert len(versao_termos(["a"])) == 12


def test_cobertura_separa_lacuna_da_lista_de_lacuna_da_busca():
    arp = [
        _arp(1, "Aquisição de notebooks", "III-computadores:notebooks@objeto"),  # achada
        _arp(2, "Aquisição de notebook", "III-computadores:notebook@objeto"),  # tem termo
        _arp(3, "Material de informática", "geral:informatica@objeto"),  # sem termo
        _arp(4, "Insumos gerais", "catmat70:pdm8435@item:central"),  # pelo catálogo
        _arp(5, "Gás de cozinha", None, ti=False),  # não é TI: fora da referência
        _arp(6, "Notebook antigo", "geral:x@objeto", fim=HOJE - timedelta(days=1)),  # vencida
    ]
    busca = [
        _busca(1, "Aquisição de notebooks", ["notebook"]),
        _busca(5, "Gás e impressora", ["impressora"]),
        _busca(9, "Toner para impressora", ["toner", "impressora"]),
    ]
    av = avaliar(arp, busca, ["notebook", "impressora", "toner"], HOJE)
    assert av.referencia == {"objeto": 3, "catalogo": 1}
    assert av.achadas == {"objeto": 1}
    assert av.cobertura == 0.25
    assert av.perdidas_com_termo == 1  # 2: o objeto tem o termo, a busca não trouxe
    assert av.palavras_sem_termo == {"informatica": 1}
    assert av.por_termo["impressora"] == [2, 1, 0]  # 5 está no ARP e não é TI
    assert av.por_termo["notebook"] == [1, 1, 1]
    assert [b["numero_controle_pncp"] for b in av.fora_do_arp] == [_controle(9)]


def test_concordancia_total_conta_cada_ata_uma_vez():
    """Revisão do Codex: uma ata TI com dois termos não pode pesar como duas."""
    arp = [_arp(1, "Notebook e toner", "geral:x@objeto"), _arp(2, "Gás", None, ti=False)]
    busca = [_busca(1, "Notebook e toner", ["notebook", "toner"]), _busca(2, "Gás", ["toner"])]
    av = avaliar(arp, busca, ["notebook", "toner"], HOJE)
    assert (av.na_sobreposicao, av.concordam) == (2, 1)
    assert "(50.0%)" in relatorio(av, HOJE, "teste", "abc", semente=1)


@pytest.mark.parametrize(
    "vigencia",
    [{"fim": HOJE - timedelta(days=1)}, {"vigente": False}],
)
def test_ata_da_busca_fora_da_vigencia_nao_conta_como_achada(vigencia):
    arp = [_arp(1, "Notebook", "geral:x@objeto")]
    av = avaliar(arp, [_busca(1, "Notebook", ["notebook"], **vigencia)], ["notebook"], HOJE)
    assert av.cobertura == 0.0 and av.na_sobreposicao == 0


def test_relatorio_neutraliza_texto_de_terceiros():
    """CPF mascarado, Markdown/HTML inertes e só links canônicos do PNCP."""
    arp = [_arp(1, "Informática do fornecedor 12345678909", "geral:informatica@objeto")]
    arp[0]["link_origem"] = "https://pncp.gov.br/app/atas/12345678909/x"
    busca = [_busca(9, "Toner | ![img](https://example.invalid/r) <b>x</b>", ["toner"])]
    texto = relatorio(avaliar(arp, busca, ["toner"], HOJE), HOJE, "teste", "abc", semente=1)
    assert "12345678909" not in texto
    assert "![img]" not in texto and "<b>" not in texto
    assert "\\!\\[img\\]" in texto and "\\<b\\>" in texto
    assert "Toner /" in texto  # barra vertical escapada na célula
    assert "**0.0%**" in texto
    assert "| informatica | 1 |" in texto
    amostra = texto.split("## Amostra para rotular")[1]
    assert f"`{_controle(9)}`" in amostra and _link(9) in amostra
