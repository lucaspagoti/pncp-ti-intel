"""Mapeia payloads do PNCP (campos confirmados por chamada real em 12/10/2026) para
as colunas estruturadas das tabelas. O payload inteiro também vai para a coluna
`raw jsonb` de cada tabela — se a API do PNCP mudar ou renomear um campo que ainda
não mapeamos aqui, o dado não se perde, só não está em coluna própria (ver
docs/PLANO.md, risco "API do PNCP muda contrato sem versionar").
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psycopg.types.json import Json

from pncp_ti.privacy import sanitizar


def _sanitizar_colunas(linha: dict[str, Any]) -> dict[str, Any]:
    return {k: sanitizar(v) if isinstance(v, str) else v for k, v in linha.items()}


def _data_ou_none(valor: Any) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor[:10])
        except ValueError as exc:
            raise ValueError("data da ata inválida") from exc
    raise ValueError("data da ata inválida")


def mapear_ata(payload: dict[str, Any]) -> dict[str, Any]:
    return _sanitizar_colunas(
        {
            "numero_controle_pncp_ata": payload["numeroControlePNCPAta"],
            "numero_controle_pncp_compra": payload.get("numeroControlePNCPCompra"),
            "numero_ata_registro_preco": payload.get("numeroAtaRegistroPreco"),
            "ano_ata": payload.get("anoAta"),
            "cnpj_orgao": payload.get("cnpjOrgao"),
            "objeto_contratacao": payload.get("objetoContratacao"),
            "cancelado": payload.get("cancelado"),
            "data_cancelamento": payload.get("dataCancelamento"),
            "data_assinatura": _data_ou_none(payload.get("dataAssinatura")),
            "vigencia_inicio": _data_ou_none(payload.get("vigenciaInicio")),
            "vigencia_fim": _data_ou_none(payload.get("vigenciaFim")),
            "data_publicacao_pncp": payload.get("dataPublicacaoPncp"),
            "data_inclusao": payload.get("dataInclusao"),
            "data_atualizacao": payload.get("dataAtualizacao"),
            "data_atualizacao_global": payload.get("dataAtualizacaoGlobal"),
            "raw": Json(sanitizar(payload)),
        }
    )


def extrair_orgao_de_ata(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Ata não embute `orgaoEntidade`; traz `cnpjOrgao`/`nomeOrgao` soltos."""
    cnpj = payload.get("cnpjOrgao")
    if not cnpj:
        return None
    return _sanitizar_colunas(
        {
            "cnpj": cnpj,
            "razao_social": payload.get("nomeOrgao"),
        }
    )
