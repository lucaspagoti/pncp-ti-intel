"""Regressões puras da proteção de documentos mantida pela infraestrutura F1."""

import pytest

from pncp_ti.privacy import identificar_fornecedor, sanitizar

CPF_A = "12300000890"
CPF_B = "12300002590"


def _fornecedor(documento: str, controle: str = "compra-1") -> dict[str, str]:
    return {
        "niFornecedor": documento,
        "tipoPessoa": "PF",
        "numeroControlePNCP": controle,
    }


def test_identidades_nao_confundem_cpfs_com_a_mesma_mascara():
    assert identificar_fornecedor(_fornecedor(CPF_A)) != identificar_fornecedor(_fornecedor(CPF_B))


def test_documento_mascarado_fica_isolado_por_contexto():
    ni = "123******90"
    assert identificar_fornecedor(_fornecedor(ni, "compra-a")) != identificar_fornecedor(
        _fornecedor(ni, "compra-b")
    )


def test_cnpj_publico_permanece_estavel():
    payload = {"niFornecedor": "12345678000190", "tipoPessoa": "PJ"}
    assert identificar_fornecedor(payload) == "cnpj:12345678000190"


def test_hmac_exige_chave_forte(monkeypatch):
    monkeypatch.setenv("PNCP_TI_IDENTITY_KEY", "short")
    with pytest.raises(RuntimeError, match="32 bytes"):
        identificar_fornecedor(_fornecedor(CPF_A))


def test_sanitizar_mascara_cpf_e_preserva_precos():
    payload = {
        "niFornecedor": CPF_A,
        "cpfResponsavel": int(CPF_B),
        "objeto": f"Contato {CPF_A}",
        "valor": 12345678901,
    }
    resultado = sanitizar(payload)
    assert CPF_A not in str(resultado)
    assert CPF_B not in str(resultado)
    assert resultado["valor"] == payload["valor"]
