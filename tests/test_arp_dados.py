"""Mapeamento, validação e classificação das atas ARP (sem rede e sem banco)."""

from datetime import timedelta

import arp_dados as d
import pytest

from pncp_ti.fontes.arp_dados import (
    CAMPOS_ATA,
    CatalogoTI,
    chave_sem_id,
    decidir_ata,
    e_candidata,
    escolher,
    mapear_ata,
    mapear_item,
    validar_contrato,
    validar_pagina,
)
from pncp_ti.fontes.arp_regra import RegraArp
from pncp_ti.fontes.siga_csv import ErroValidacao

CATALOGO = CatalogoTI(pdms=frozenset({239, 283}), servicos={1260: 8713})


def test_ata_vigente_e_mapeada_com_link_e_licitacao():
    a = mapear_ata(d.ata("1", "Aquisição de notebooks"), d.hoje())
    assert a.id_origem == d.id_ata("1")
    assert a.vigente_na_origem
    assert a.licitacao == "00010/2026"
    assert a.orgao == "ORGAO TESTE"
    assert a.link_origem.startswith("https://pncp.gov.br/app/atas/")
    assert a.fim >= d.hoje()


@pytest.mark.parametrize(
    "extra",
    [{"status": "Cancelada"}, {"excluida": True}],
    ids=["cancelada", "excluida"],
)
def test_ata_cancelada_ou_excluida_nao_e_vigente_na_origem(extra):
    assert not mapear_ata(d.ata("2", "Notebooks", **extra), d.hoje()).vigente_na_origem


def test_ata_sem_fim_ou_sem_id_e_descartada_e_data_absurda_falha():
    bruto = d.ata("3", "Notebooks")
    del bruto["dataVigenciaFinal"]
    assert mapear_ata(bruto, d.hoje()) is None
    longe = d.ata("4", "Notebooks", fim=d.hoje() + timedelta(days=5000))
    with pytest.raises(ErroValidacao) as erro:
        mapear_ata(longe, d.hoje())
    assert erro.value.tipo == "data_anomala"


def test_cpf_de_fornecedor_pf_nao_vai_para_chave_nem_para_identidade():
    pf = mapear_item(d.item("1", "1", "Serviço", ni=d.CPF_FICTICIO))
    assert pf.id_fornecedor.startswith("hmac:")
    assert d.CPF_FICTICIO not in pf.chave + pf.id_fornecedor + pf.fornecedor + pf.descricao
    pj = mapear_item(d.item("1", "2", "Notebook"))
    assert pj.id_fornecedor == f"cnpj:{d.CNPJ_FICTICIO}"
    assert pf.chave != pj.chave


def test_cpf_em_texto_livre_e_mascarado():
    bruto = d.item("1", "1", f"Notebook do servidor CPF {d.CPF_FICTICIO}")
    assert d.CPF_FICTICIO not in mapear_item(bruto).descricao


def test_item_excluido_e_preco_zero():
    assert mapear_item(d.item("1", "1", "x", excluido=True)) is None
    assert not mapear_item(d.item("1", "1", "x", valor=0.0)).valor_valido


def test_validar_pagina_rejeita_envelope_ruim_e_pagina_vazia_no_meio():
    with pytest.raises(ErroValidacao):
        validar_pagina([], 1)
    with pytest.raises(ErroValidacao) as erro:
        validar_pagina(d.envelope([], total=900, paginas=2), 2)
    assert erro.value.tipo == "pagina_vazia"
    registros, total, paginas = validar_pagina(d.envelope([d.ata("1", "x")]), 1)
    assert (len(registros), total, paginas) == (1, 1, 1)


def test_contrato_falha_se_campo_some_da_api():
    bruto = d.ata("1", "x")
    del bruto["numeroControlePncpAta"]
    with pytest.raises(ErroValidacao) as erro:
        validar_contrato([bruto], CAMPOS_ATA)
    assert erro.value.tipo == "contrato"


def test_candidata_generosa_pega_objeto_generico_com_termo_de_ti():
    assert e_candidata("Registro de preços para aquisição de computadores")
    assert not e_candidata("Registro de preços para gêneros alimentícios")


def test_anexo_decide_primeiro_e_motivo_registra_a_regra():
    decisao = decidir_ata("Aquisição de notebooks e software", [], CATALOGO)
    assert decisao.is_ti and "@objeto" in decisao.motivo


def test_catalogo_acrescenta_ata_sem_sinal_no_objeto():
    itens = [mapear_item(d.item("1", "1", "Teclado", pdm=239, nome_pdm="XPTO"))]
    decisao = decidir_ata("Material diverso de consumo", itens, CATALOGO)
    assert decisao.is_ti and decisao.motivo.startswith("catmat70:pdm239@item")
    servico = [mapear_item(d.item("1", "2", "Reparo", tipo="Serviço", codigo=1260, pdm=None))]
    motivo = decidir_ata("Serviços gerais", servico, CATALOGO).motivo
    assert motivo.startswith("catser8713:servico1260@item")


def test_catalogo_nao_reverte_exclusao_explicita_do_anexo():
    itens = [mapear_item(d.item("1", "1", "Nobreak", pdm=239))]
    decisao = decidir_ata("Aquisição de nobreak e estabilizadores", itens, CATALOGO)
    assert not decisao.is_ti
    assert decisao.motivo.startswith("excluido:")


def test_item_fora_do_catalogo_nao_vira_ti():
    itens = [mapear_item(d.item("1", "1", "Caneta", pdm=77777))]
    assert not decidir_ata("Material de expediente", itens, CATALOGO).is_ti


def test_inicio_preenchido_e_invalido_descarta_a_ata():
    bruto = d.ata("9", "Notebooks")
    bruto["dataVigenciaInicial"] = "2026-02-31"
    assert mapear_ata(bruto, d.hoje()) is None


def test_cpfs_distintos_com_mesma_mascara_nao_colidem_na_chave():
    # 123.***.**9-09 nos dois: só os dígitos do meio mudam.
    a = mapear_item(d.item("1", "1", "Serviço", ni="12345678909"))
    b = mapear_item(d.item("1", "1", "Serviço", ni="12300000909"))
    assert a.chave != b.chave
    assert "12345678909" not in a.chave and "12300000909" not in b.chave


def test_ata_sem_id_tem_chave_natural_e_aceita_id_recuperado():
    bruto = d.ata("7", "Aquisição de notebooks")
    bruto["numeroControlePncpAta"] = None
    assert mapear_ata(bruto, d.hoje()) is None
    inicio = (d.hoje() - timedelta(days=30)).isoformat()
    assert chave_sem_id(bruto) == ("999999", "00010", "2026", inicio, "7/2026")
    recuperada = mapear_ata(bruto, d.hoje(), id_origem="id-recuperado")
    assert recuperada.id_origem == "id-recuperado"
    del bruto["numeroCompra"]
    assert chave_sem_id(bruto) is None


@pytest.mark.parametrize("excluida_primeiro", [True, False])
def test_repetida_excluida_nao_derruba_a_vigente(excluida_primeiro):
    valida = mapear_ata(d.ata("8", "Notebooks", atualizado="2025-11-07T12:31:28"), d.hoje())
    excluida = mapear_ata(
        d.ata("8", "Notebooks", excluida=True, atualizado="2026-06-09T07:30:21"), d.hoje()
    )
    par = (excluida, valida) if excluida_primeiro else (valida, excluida)
    assert escolher(*par) is valida


def test_entre_repetidas_no_mesmo_estado_fica_a_mais_recente():
    velha = mapear_ata(d.ata("9", "Notebooks", atualizado="2026-01-01T00:00:00"), d.hoje())
    nova = mapear_ata(d.ata("9", "Notebooks", atualizado="2026-02-01T00:00:00"), d.hoje())
    assert escolher(velha, nova) is nova
    assert escolher(nova, velha) is nova


REGRA = RegraArp(limiar_proporcao=0.5, pdms_centrais=frozenset({8435}))


def _itens(*pdms: int):
    return [mapear_item(d.item("1", str(n), f"Item {n}", pdm=p)) for n, p in enumerate(pdms, 1)]


def test_item_de_ti_incidental_nao_classifica_a_ata():
    itens = _itens(239, 1, 2, 3)  # 1 de 4 itens de TI, nenhum central
    decisao = decidir_ata("Material de expediente", itens, CATALOGO, REGRA)
    assert not decisao.is_ti and decisao.motivo == "catalogo_incidental"


def test_proporcao_no_limiar_classifica_e_motivo_registra_a_conta():
    decisao = decidir_ata("Material diverso", _itens(239, 283, 1, 2), CATALOGO, REGRA)
    assert decisao.is_ti and decisao.motivo.endswith(":compra2de4")  # sem compra: a própria ata
    assert not decidir_ata("Material diverso", _itens(239, 1, 2, 3, 4), CATALOGO, REGRA).is_ti


def test_proporcao_e_da_compra_e_nao_da_ata_do_fornecedor():
    """ADR 0025, item 7: uma ata por fornecedor; mouse pad 1 de 1 numa compra genérica."""
    so_mouse_pad = _itens(239)
    incidental = decidir_ata("Material de expediente", so_mouse_pad, CATALOGO, REGRA, (1, 10))
    assert not incidental.is_ti and incidental.motivo == "catalogo_incidental"
    pela_compra = decidir_ata("Material diverso", so_mouse_pad, CATALOGO, REGRA, (3, 6))
    assert pela_compra.is_ti and pela_compra.motivo == "catmat70:pdm239@item:compra3de6"


def test_dois_itens_de_ti_na_ata_classificam_mesmo_em_compra_generica():
    decisao = decidir_ata("Material diverso", _itens(239, 283), CATALOGO, REGRA, (2, 90))
    assert decisao.is_ti and decisao.motivo == "catmat70:pdm239@item:ata2itens"


def test_pdm_central_classifica_mesmo_com_um_item_entre_muitos():
    catalogo = CatalogoTI(pdms=frozenset({239, 283, 8435}), servicos={1260: 8713})
    itens = _itens(8435, *range(1, 10))
    decisao = decidir_ata("Material diverso", itens, catalogo, REGRA)
    assert decisao.is_ti and decisao.motivo.endswith(":central")


def test_objeto_de_ti_vale_mesmo_sem_item_de_ti():
    assert decidir_ata("Aquisição de notebooks", _itens(1, 2, 3), CATALOGO, REGRA).is_ti


def test_proporcao_conta_itens_e_nao_linhas_de_fornecedor():
    """Revisão do Codex: item com 2 fornecedores são 2 linhas, mas 1 item."""
    ti = [mapear_item(d.item("1", str(n), f"TI {n}", pdm=239 if n < 3 else 1)) for n in (1, 2)]
    nao_ti = [
        mapear_item(d.item("1", str(n), f"Outro {n}", pdm=1, ni=ni))
        for n in (3, 4)
        for ni in ("11222333000181", "99888777000161")
    ]
    catalogo = CatalogoTI(pdms=frozenset({239}), servicos={})
    decisao = decidir_ata("Material diverso", ti + nao_ti, catalogo, REGRA)
    assert decisao.is_ti and decisao.motivo.endswith(":compra2de4")  # 2 de 4 itens, não 2 de 6


def test_motivo_central_aponta_o_item_central_e_nao_o_primeiro_item_de_ti():
    catalogo = CatalogoTI(pdms=frozenset({283, 8435}), servicos={})
    itens = _itens(283, 8435, 1, 2, 3, 4)
    decisao = decidir_ata("Material diverso", itens, catalogo, REGRA)
    assert decisao.is_ti and decisao.motivo == "catmat70:pdm8435@item:central"
