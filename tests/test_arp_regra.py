"""Regra de TI do ARP pelo catálogo (R2.1): arquivo de parâmetros e corte."""

import json

import pytest

from pncp_ti.fontes.arp_regra import CAMINHO, RegraArp, carregar_regra
from pncp_ti.fontes.siga_csv import ErroValidacao


def test_arquivo_versionado_carrega_e_tem_os_pdms_centrais_esperados():
    regra = carregar_regra()
    assert 0 < regra.limiar_proporcao <= 1
    assert {8435, 9726, 5522, 237} <= regra.pdms_centrais  # notebook, switch, roteador
    assert 283 not in regra.pdms_centrais  # chaveadoras: ruído da classe de computadores
    assert CAMINHO.name == "regra_ti_arp.json"


@pytest.mark.parametrize(
    ("ti_ata", "ti_compra", "total_compra", "central", "esperado"),
    [
        (1, 1, 2, False, "compra1de2"),  # exatamente no limiar
        (1, 1, 3, False, None),
        (1, 3, 6, False, "compra3de6"),  # a compra passa mesmo com 1 item na ata
        (1, 1, 10, True, "central"),  # central ignora a proporção
        (0, 0, 10, True, None),  # central sem item de TI não existe
        (2, 2, 90, False, "ata2itens"),  # 2 itens de TI na própria ata, compra genérica
        (1, 1, 0, False, None),  # total desconhecido e 1 item: não passa
        (3, 3, 0, False, "ata3itens"),
        (3, 3, 0, True, "central"),
    ],
)
def test_corte(ti_ata, ti_compra, total_compra, central, esperado):
    regra = RegraArp(0.5, frozenset({1}), minimo_itens_ata=2)
    assert regra.motivo(ti_ata, ti_compra, total_compra, central) == esperado
    assert regra.passa(ti_ata, ti_compra, total_compra, central) is (esperado is not None)


def test_versao_muda_com_os_parametros():
    assert RegraArp(0.5, frozenset({1})).versao() != RegraArp(0.6, frozenset({1})).versao()
    assert RegraArp(0.5, frozenset({1})).versao() != RegraArp(0.5, frozenset({1, 2})).versao()
    assert RegraArp(0.5, frozenset({1}), 2).versao() != RegraArp(0.5, frozenset({1}), 3).versao()


def test_arquivo_versionado_exige_dois_itens_na_ata():
    assert carregar_regra().minimo_itens_ata == 2


@pytest.mark.parametrize(
    "conteudo",
    [
        "{",
        "{}",
        '{"limiar_proporcao": 0, "pdms_centrais": [], "minimo_itens_ata": 2}',
        '{"limiar_proporcao": "x"}',
        '{"limiar_proporcao": 0.5, "pdms_centrais": []}',
        '{"limiar_proporcao": 0.5, "pdms_centrais": [], "minimo_itens_ata": 0}',
        '{"limiar_proporcao": 0.5, "pdms_centrais": [], "minimo_itens_ata": 1.5}',
    ],
)
def test_arquivo_invalido_falha_alto(tmp_path, conteudo):
    arquivo = tmp_path / "regra.json"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ErroValidacao) as erro:
        carregar_regra(arquivo)
    assert erro.value.tipo == "regra"


def test_arquivo_ausente_falha_alto(tmp_path):
    with pytest.raises(ErroValidacao):
        carregar_regra(tmp_path / "nao_existe.json")
    assert json.loads(CAMINHO.read_text(encoding="utf-8"))["versao"] >= 1
