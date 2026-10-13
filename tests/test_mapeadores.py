"""Mapeamento e filtro de atas dentro do recorte da ADR 0015."""

from pncp_ti.classificar.regra import objeto_ata_tem_sinal_ti
from pncp_ti.ingest.mapeadores import extrair_orgao_de_ata, mapear_ata

ATA = {
    "numeroControlePNCPAta": "12345678000199-1-000001/2026-000001",
    "numeroControlePNCPCompra": "12345678000199-1-000001/2026",
    "numeroAtaRegistroPreco": "1/2026",
    "anoAta": 2026,
    "cnpjOrgao": "12345678000199",
    "objetoContratacao": "Aquisição de computadores e notebooks",
    "cancelado": False,
    "vigenciaInicio": "2026-01-01",
    "vigenciaFim": "2026-12-31",
}


def test_mapear_ata_preserva_campos_e_payload():
    linha = mapear_ata(ATA)
    assert linha["numero_controle_pncp_ata"] == ATA["numeroControlePNCPAta"]
    assert linha["numero_controle_pncp_compra"] == ATA["numeroControlePNCPCompra"]
    assert linha["objeto_contratacao"] == ATA["objetoContratacao"]
    assert linha["raw"].obj["numeroControlePNCPAta"] == ATA["numeroControlePNCPAta"]
    assert str(linha["vigencia_inicio"]) == ATA["vigenciaInicio"]


def test_mapear_ata_normaliza_data_com_horario_para_coluna_date():
    linha = mapear_ata({**ATA, "vigenciaInicio": "2026-01-01T00:00:00Z"})
    assert str(linha["vigencia_inicio"]) == "2026-01-01"


def test_extrair_orgao_da_ata():
    assert extrair_orgao_de_ata(ATA) == {
        "cnpj": ATA["cnpjOrgao"],
        "razao_social": None,
    }
    assert extrair_orgao_de_ata({}) is None


def test_filtro_generoso_de_objeto_ata():
    for objeto in (
        "Serviços de tecnologia da informação",
        "Aquisição de microinformática para as unidades",
        "Fornecimento de equipamentos de TIC e rede de dados",
        "Pacote de telefonia e internet corporativa",
    ):
        assert objeto_ata_tem_sinal_ti(objeto)


def test_filtro_nao_classifica_texto_sem_sinal_de_ti():
    assert not objeto_ata_tem_sinal_ti("Aquisição de mobiliário escolar")
    assert not objeto_ata_tem_sinal_ti(None)
