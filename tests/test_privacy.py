"""Regressões de privacidade, identidade e completude dos dados (ADR 0013)."""

import json

from pncp_ti.db import upsert
from pncp_ti.ingest.mapeadores import (
    extrair_fornecedor,
    extrair_orgao,
    extrair_orgao_de_ata,
    mapear_contrato,
)
from pncp_ti.privacy import identificar_fornecedor, sanitizar

CPF_A = "12300000890"
CPF_B = "12300002590"


def contrato(cpf, numero="privacy-a"):
    return {"numeroControlePNCP": numero, "tipoPessoa": "PF", "niFornecedor": cpf}


def test_identidade_nao_confunde_cpfs_com_a_mesma_mascara():
    a, b = mapear_contrato(contrato(CPF_A)), mapear_contrato(contrato(CPF_B))
    assert a["ni_fornecedor"] == b["ni_fornecedor"]
    assert a["fornecedor_id"] != b["fornecedor_id"]
    assert identificar_fornecedor(contrato(CPF_A)) == a["fornecedor_id"]
    assert CPF_A not in a["fornecedor_id"]


def test_identidade_de_mascara_upstream_e_isolada_por_contrato():
    ni = "123******90"
    assert identificar_fornecedor(contrato(ni, "a")) != identificar_fornecedor(contrato(ni, "b"))
    assert mapear_contrato(contrato(ni))["ni_fornecedor"] == ni


def test_hmac_exige_chave_forte(monkeypatch):
    import pytest

    monkeypatch.setenv("PNCP_TI_IDENTITY_KEY", "short")
    with pytest.raises(RuntimeError, match="32 bytes"):
        identificar_fornecedor(contrato(CPF_A))


def test_cpf_subcontratado_campos_novos_e_texto_sem_modificar_entrada():
    payload = {
        **contrato(CPF_A),
        "niFornecedorSubContratado": CPF_B,
        "tipoPessoaSubContratada": "PF",
        "objetoContrato": f"Contato {CPF_A} e 123.000.025-90",
        "novo": [{"cpfResponsavel": int(CPF_A), "outro": CPF_B}],
        "valorGlobal": 12345678901,
    }
    row = mapear_contrato(payload)
    raw = row["raw"].obj
    persisted = json.dumps(raw) + row["objeto_contrato"]
    assert CPF_A not in persisted
    assert CPF_B not in persisted
    assert "123.000.025-90" not in persisted
    assert raw["niFornecedorSubContratado"] == "123******90"
    assert raw["valorGlobal"] == payload["valorGlobal"]
    assert row["valor_global"] == payload["valorGlobal"]
    assert payload["niFornecedorSubContratado"] == CPF_B
    assert (
        sanitizar({"niFornecedor": 1234567890, "tipoPessoa": "PF"})["niFornecedor"] == "123*****90"
    )


async def test_fornecedores_distintos_ficam_em_contratos_distintos(conn_ingest):
    for cpf, name in ((CPF_A, "privacy-a"), (CPF_B, "privacy-b")):
        payload = contrato(cpf, name)
        await upsert(conn_ingest, "fornecedores", "fornecedor_id", extrair_fornecedor(payload))
        await upsert(conn_ingest, "contratos", "numero_controle_pncp", mapear_contrato(payload))
    rows = await (
        await conn_ingest.execute(
            "SELECT c.numero_controle_pncp, f.fornecedor_id, f.ni FROM contratos c "
            "JOIN fornecedores f ON f.fornecedor_id=c.fornecedor_id "
            "WHERE c.numero_controle_pncp IN ('privacy-a','privacy-b')"
        )
    ).fetchall()
    assert len(rows) == 2
    assert len({r["fornecedor_id"] for r in rows}) == 2
    assert len({r["ni"] for r in rows}) == 1


async def test_orgao_incompleto_nao_apaga_dados_conhecidos(conn_ingest):
    orgao = {"cnpj": "12345678000190", "razaoSocial": "Teste", "poderId": "E", "esferaId": "M"}
    await upsert(conn_ingest, "orgaos", "cnpj", extrair_orgao({"orgaoEntidade": orgao}))
    await upsert(
        conn_ingest,
        "orgaos",
        "cnpj",
        extrair_orgao_de_ata({"cnpjOrgao": orgao["cnpj"], "nomeOrgao": "Atualizado"}),
    )
    await upsert(
        conn_ingest, "orgaos", "cnpj", extrair_orgao({"orgaoEntidade": {"cnpj": orgao["cnpj"]}})
    )
    row = await (
        await conn_ingest.execute("SELECT * FROM orgaos WHERE cnpj=%s", (orgao["cnpj"],))
    ).fetchone()
    assert (row["poder_id"], row["esfera_id"], row["razao_social"]) == ("E", "M", "Atualizado")
