"""Mapeia payloads do PNCP (campos confirmados por chamada real em 12/10/2026) para
as colunas estruturadas das tabelas. O payload inteiro também vai para a coluna
`raw jsonb` de cada tabela — se a API do PNCP mudar ou renomear um campo que ainda
não mapeamos aqui, o dado não se perde, só não está em coluna própria (ver
docs/PLANO.md, risco "API do PNCP muda contrato sem versionar").
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from pncp_ti.mask import mascarar_ni


def _int_ou_none(valor: Any) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def mapear_contratacao(payload: dict[str, Any]) -> dict[str, Any]:
    orgao = payload.get("orgaoEntidade") or {}
    unidade = payload.get("unidadeOrgao") or {}
    return {
        "numero_controle_pncp": payload["numeroControlePNCP"],
        "cnpj_orgao": orgao.get("cnpj"),
        "uf_sigla": unidade.get("ufSigla"),
        "municipio_nome": unidade.get("municipioNome"),
        "codigo_ibge_municipio": _int_ou_none(unidade.get("codigoIbge")),
        "codigo_unidade": unidade.get("codigoUnidade"),
        "nome_unidade": unidade.get("nomeUnidade"),
        "ano_compra": payload.get("anoCompra"),
        "sequencial_compra": payload.get("sequencialCompra"),
        "numero_compra": payload.get("numeroCompra"),
        "processo": payload.get("processo"),
        "objeto_compra": payload.get("objetoCompra"),
        "modalidade_id": payload.get("modalidadeId"),
        "modalidade_nome": payload.get("modalidadeNome"),
        "situacao_compra_id": payload.get("situacaoCompraId"),
        "situacao_compra_nome": payload.get("situacaoCompraNome"),
        "srp": payload.get("srp"),
        "valor_total_estimado": payload.get("valorTotalEstimado"),
        "valor_total_homologado": payload.get("valorTotalHomologado"),
        "data_publicacao_pncp": payload.get("dataPublicacaoPncp"),
        "data_inclusao": payload.get("dataInclusao"),
        "data_atualizacao": payload.get("dataAtualizacao"),
        "data_atualizacao_global": payload.get("dataAtualizacaoGlobal"),
        "data_abertura_proposta": payload.get("dataAberturaProposta"),
        "data_encerramento_proposta": payload.get("dataEncerramentoProposta"),
        "link_sistema_origem": payload.get("linkSistemaOrigem"),
        "link_processo_eletronico": payload.get("linkProcessoEletronico"),
        "raw": Json(payload),
    }


def extrair_orgao(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Órgão embutido em contratações e contratos — objeto `orgaoEntidade`."""
    orgao = payload.get("orgaoEntidade") or {}
    cnpj = orgao.get("cnpj")
    if not cnpj:
        return None
    return {
        "cnpj": cnpj,
        "razao_social": orgao.get("razaoSocial"),
        "poder_id": orgao.get("poderId"),
        "esfera_id": orgao.get("esferaId"),
    }


def mapear_ata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "numero_controle_pncp_ata": payload["numeroControlePNCPAta"],
        "numero_controle_pncp_compra": payload.get("numeroControlePNCPCompra"),
        "numero_ata_registro_preco": payload.get("numeroAtaRegistroPreco"),
        "ano_ata": payload.get("anoAta"),
        "cnpj_orgao": payload.get("cnpjOrgao"),
        "objeto_contratacao": payload.get("objetoContratacao"),
        "cancelado": payload.get("cancelado"),
        "data_cancelamento": payload.get("dataCancelamento"),
        "data_assinatura": payload.get("dataAssinatura"),
        "vigencia_inicio": payload.get("vigenciaInicio"),
        "vigencia_fim": payload.get("vigenciaFim"),
        "data_publicacao_pncp": payload.get("dataPublicacaoPncp"),
        "data_inclusao": payload.get("dataInclusao"),
        "data_atualizacao": payload.get("dataAtualizacao"),
        "data_atualizacao_global": payload.get("dataAtualizacaoGlobal"),
        "raw": Json(payload),
    }


def extrair_orgao_de_ata(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Ata não embute `orgaoEntidade`; traz `cnpjOrgao`/`nomeOrgao` soltos."""
    cnpj = payload.get("cnpjOrgao")
    if not cnpj:
        return None
    return {
        "cnpj": cnpj,
        "razao_social": payload.get("nomeOrgao"),
        "poder_id": None,
        "esfera_id": None,
    }


def _raw_sem_cpf(payload: dict[str, Any]) -> dict[str, Any]:
    """Cópia do payload com `niFornecedor` mascarado antes de ir pro `raw jsonb`.

    A coluna `raw` guarda o payload por completo de propósito (ver docstring do
    módulo), mas isso não pode incluir um CPF sem máscara — "CPFs sempre
    mascarados" é regra fixa do CLAUDE.md e vale pra toda coluna, não só pra
    `ni_fornecedor` estruturada.
    """
    if "niFornecedor" not in payload:
        return payload
    copia = dict(payload)
    copia["niFornecedor"] = mascarar_ni(payload.get("niFornecedor"), payload.get("tipoPessoa"))
    return copia


def mapear_contrato(payload: dict[str, Any]) -> dict[str, Any]:
    orgao = payload.get("orgaoEntidade") or {}
    return {
        "numero_controle_pncp": payload["numeroControlePNCP"],
        # Atenção: a API usa "Pncp" minúsculo aqui (vs "PNCP" no payload de
        # contratação/ata) — inconsistência real do PNCP, confirmada por chamada.
        "numero_controle_pncp_compra": payload.get("numeroControlePncpCompra"),
        "numero_controle_pncp_ata": payload.get("numeroControlePncpAta"),
        "cnpj_orgao": orgao.get("cnpj"),
        "ni_fornecedor": mascarar_ni(payload.get("niFornecedor"), payload.get("tipoPessoa")),
        "ano_contrato": payload.get("anoContrato"),
        "sequencial_contrato": payload.get("sequencialContrato"),
        "numero_contrato_empenho": payload.get("numeroContratoEmpenho"),
        "processo": payload.get("processo"),
        "objeto_contrato": payload.get("objetoContrato"),
        "valor_inicial": payload.get("valorInicial"),
        "valor_parcela": payload.get("valorParcela"),
        "valor_global": payload.get("valorGlobal"),
        "valor_acumulado": payload.get("valorAcumulado"),
        "numero_parcelas": payload.get("numeroParcelas"),
        "data_assinatura": payload.get("dataAssinatura"),
        "data_vigencia_inicio": payload.get("dataVigenciaInicio"),
        "data_vigencia_fim": payload.get("dataVigenciaFim"),
        "data_publicacao_pncp": payload.get("dataPublicacaoPncp"),
        "data_atualizacao": payload.get("dataAtualizacao"),
        "data_atualizacao_global": payload.get("dataAtualizacaoGlobal"),
        "raw": Json(_raw_sem_cpf(payload)),
    }


def extrair_fornecedor(payload: dict[str, Any]) -> dict[str, Any] | None:
    ni = payload.get("niFornecedor")
    if not ni:
        return None
    tipo = payload.get("tipoPessoa")
    return {
        "ni": mascarar_ni(ni, tipo),
        "tipo_pessoa": tipo,
        "razao_social_nome": payload.get("nomeRazaoSocialFornecedor"),
    }
