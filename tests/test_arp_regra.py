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
    ("ti", "total", "central", "esperado"),
    [
        (1, 2, False, True),  # exatamente no limiar
        (1, 3, False, False),
        (1, 10, True, True),  # central ignora a proporção
        (0, 10, True, False),  # central sem item de TI não existe
        (3, 0, False, False),  # total desconhecido: só passa pelo central
        (3, 0, True, True),
    ],
)
def test_corte(ti, total, central, esperado):
    regra = RegraArp(0.5, frozenset({1}))
    assert regra.passa(ti, total, central) is esperado


def test_versao_muda_com_os_parametros():
    assert RegraArp(0.5, frozenset({1})).versao() != RegraArp(0.6, frozenset({1})).versao()
    assert RegraArp(0.5, frozenset({1})).versao() != RegraArp(0.5, frozenset({1, 2})).versao()


@pytest.mark.parametrize(
    "conteudo",
    ["{", "{}", '{"limiar_proporcao": 0, "pdms_centrais": []}', '{"limiar_proporcao": "x"}'],
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


@pytest.mark.parametrize(
    ("ti", "total", "central", "esperado"),
    [
        (1, 4, False, True),  # 25% = metade do limiar: passa a conferir
        (1, 5, False, False),  # 20%: abaixo da folga
        (1, 0, False, True),  # contagem da listagem desconhecida: confere
        (3, 2, False, True),  # achou mais itens de TI do que a listagem declara: confere
        (1, 10, True, True),
        (0, 0, False, False),
    ],
)
def test_pre_corte_tem_folga_sobre_a_contagem_da_listagem(ti, total, central, esperado):
    assert RegraArp(0.5, frozenset({1})).passa_pre(ti, total, central) is esperado
