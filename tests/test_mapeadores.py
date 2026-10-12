"""`raw jsonb` guarda o payload inteiro de propósito (ver mapeadores.py), mas
isso não pode incluir um CPF sem máscara — regra fixa do CLAUDE.md vale pra
toda coluna, não só pra `ni_fornecedor` estruturada.
"""

from pncp_ti.ingest.mapeadores import mapear_contrato


def test_raw_do_contrato_nao_guarda_cpf_sem_mascara():
    payload = {
        "numeroControlePNCP": "x",
        "tipoPessoa": "PF",
        "niFornecedor": "12345678901",
    }
    linha = mapear_contrato(payload)

    assert linha["ni_fornecedor"] == "123******01"
    assert linha["raw"].obj["niFornecedor"] == "123******01"


def test_raw_do_contrato_com_fornecedor_pj_fica_intacto():
    payload = {
        "numeroControlePNCP": "x",
        "tipoPessoa": "PJ",
        "niFornecedor": "12345678000190",
    }
    linha = mapear_contrato(payload)

    assert linha["raw"].obj["niFornecedor"] == "12345678000190"
