"""Regra de TI do SIGA, baseada no Anexo Único da IN PRODERJ/PRE nº 05/2024."""

import pytest

from pncp_ti.classificar import in05
from pncp_ti.classificar.in05 import CATEGORIAS_FORA_DE_ESCOPO, classificar_ata, nome_de_catalogo


@pytest.mark.parametrize(
    ("objeto", "nomes", "categoria"),
    [
        ("OUTSOURCING DE IMPRESSÃO", [], "III-computadores"),
        ("Aquisição de notebooks", [], "III-computadores"),
        ("FIREWALL AQUISIÇÃO", [], "I-seguranca"),
        ("HIPERCONVERGÊNCIA DELL VMWARE", [], "II-infra"),
        ("SOFTWARE DE BACKUP", [], "II-software-infra"),
        ("LICENCIAMENTO ORCLE", ["SERVICOS DE LICENCAS DE SOFTWARES"], "VI-software"),
        ("PLATAFORMA WEB", ["OUTROS SERVICOS INFRAESTRUTURA EM TECNOLOGIA DA INFORMACAO"], "geral"),
        ("SOLUÇÃO EM NUVEM", [], "IV-nuvem"),
        ("SERVIÇO DE VIDEOCONFERÊNCIA", [], "VII-video"),
        ("X", ["MONITOR"], "III-computadores"),
        ("X", ["MONITOR DE VIDEO"], "III-computadores"),
    ],
)
def test_exemplos_do_anexo_sao_ti(objeto, nomes, categoria):
    decisao = classificar_ata(objeto, nomes)
    assert decisao.is_ti, decisao.motivo
    assert decisao.motivo.startswith(categoria + ":")


@pytest.mark.parametrize(
    ("objeto", "nomes"),
    [
        ("MEDICAMENTO", ["DIPIRONA"]),
        ("AQUISIÇÃO DE MONITOR BIS", ["MONITOR NIVEL DE CONSCIENCIA"]),
        ("MONITOR MULTIPARAMETRICO", ["MONITOR MULTIPARAMETRICO"]),
        ("AQUISIÇÃO DE EQUIPAMENTOS LABORATORIAIS", ["TURBIDIMETRO"]),
        ("TOMOGRAFIA", ["TOMOGRAFO"]),
        ("LICENCIAMENTO AMBIENTAL", []),
        ("", []),
    ],
)
def test_nao_ti(objeto, nomes):
    decisao = classificar_ata(objeto, nomes)
    assert not decisao.is_ti
    assert decisao.motivo == "sem_sinal"


def test_menção_incidental_na_especificacao_do_item_nao_conta():
    # `nome_de_catalogo` corta no " - ": a especificação (com "SOFTWARE") nunca é lida.
    nome = nome_de_catalogo("TURBIDIMETRO - FAIXA: 0-1000, SOFTWARE: INCLUSO")
    assert nome == "TURBIDIMETRO"
    assert not classificar_ata("EQUIPAMENTOS LABORATORIAIS", [nome]).is_ti


@pytest.mark.parametrize(
    ("objeto", "nomes", "fragmento"),
    [
        ("VOIP", ["SERVICOS DE TELEFONIA"], "I-telecom"),
        ("PONTOS LÓGICOS E ELÉTRICOS", ["CERTIFICACAO CABEAMENTO OTICO"], "VIII-rede-fisica"),
        ("SISTEMA DE VIDEOMONITORAMENTO", [], "VII-videomonitoramento"),
    ],
)
def test_categorias_do_anexo_excluidas_por_decisao_do_lucas(objeto, nomes, fragmento):
    assert fragmento in CATEGORIAS_FORA_DE_ESCOPO
    decisao = classificar_ata(objeto, nomes)
    assert not decisao.is_ti
    assert decisao.motivo.startswith(f"excluido:fora_de_escopo:{fragmento}")


@pytest.mark.parametrize("objeto", ["Aquisição de Nobreaks", "RP de Drones", "CATRACA - CFTV"])
def test_termos_fora_do_anexo_excluem_mesmo_com_item_de_ti(objeto):
    decisao = classificar_ata(objeto, ["SERVICOS DE LICENCAS DE SOFTWARES"])
    assert not decisao.is_ti
    assert decisao.motivo.startswith("excluido:fora_do_anexo:")


def test_item_de_ti_dentro_do_escopo_prevalece_sobre_objeto_de_categoria_excluida():
    # Caso real do PRODERJ: objeto de reconhecimento facial, item de suporte em TI.
    # A decisão fica aberta para o Lucas na rotulagem; a regra segue a ordem documentada.
    decisao = classificar_ata(
        "RECONHECIMENTO FACIAL", ["SERVICOS SUPORTE EM TECNOLOGIA DA INFORMACAO"]
    )
    assert decisao.is_ti and decisao.motivo.endswith("@item")


def test_toda_categoria_fora_de_escopo_existe():
    assert CATEGORIAS_FORA_DE_ESCOPO <= set(in05.CATEGORIAS)
