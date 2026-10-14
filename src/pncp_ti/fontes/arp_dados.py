"""Mapeamento, validação e classificação das atas do Compras.gov.br (módulo ARP, ADR 0020).

Só funções puras, sem rede nem banco: `fontes.arp` faz a E/S e chama estas funções.
O texto da API é dado de terceiros: passa por `sanitizar` (CPF mascarado) antes de
virar valor ou chave.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pncp_ti.classificar.in05 import Decisao, classificar_ata, normalizar
from pncp_ti.classificar.regra import objeto_ata_tem_sinal_ti
from pncp_ti.fontes.siga_csv import ErroValidacao
from pncp_ti.mask import mascarar_ni
from pncp_ti.privacy import identificar_fornecedor, sanitizar

# Campos sem os quais o contrato da API mudou: falhar alto em vez de publicar vazio.
CAMPOS_ATA = ("numeroControlePncpAta", "dataVigenciaFinal", "objeto", "statusAta", "ataExcluido")
CAMPOS_ITEM = ("numeroControlePncpAta", "numeroItem", "valorUnitario", "niFornecedor")

LIMITE_TEXTO = 4000
FIM_ANOMALO_DIAS = 1100  # janelas cobrem 3 anos; além disso a data é anomalia, não ata vigente


@dataclass(frozen=True, slots=True)
class AtaArp:
    id_origem: str  # numeroControlePncpAta
    numero: str
    unidade_gerenciadora: str
    orgao: str
    objeto: str
    licitacao: str
    inicio: date | None
    fim: date
    status_origem: str
    vigente_na_origem: bool
    link_origem: str
    numero_controle_pncp_compra: str
    valor_total: Decimal | None
    quantidade_itens: int | None
    atualizado_em: str


@dataclass(frozen=True, slots=True)
class ItemArp:
    chave: str
    ata_id_origem: str
    id_item: str
    descricao: str
    nome_catalogo: str  # nome do PDM (material) ou vazio
    tipo_item: str
    codigo_catalogo: int | None
    codigo_pdm: int | None
    nome_pdm: str
    id_fornecedor: str | None
    fornecedor: str
    quantidade: Decimal | None
    valor_unitario: Decimal | None
    valor_valido: bool
    quantidade_empenhada: Decimal | None
    maximo_adesao: Decimal | None


@dataclass(frozen=True, slots=True)
class CatalogoTI:
    """Códigos de catálogo tratados como TI (ADR 0006, `classificar/regra.py`)."""

    pdms: frozenset[int]  # PDMs do CATMAT grupo 70
    servicos: Mapping[int, int]  # codigoServico -> classe CATSER de TI

    def versao(self) -> str:
        conteudo = repr((sorted(self.pdms), sorted(self.servicos.items())))
        return hashlib.sha256(conteudo.encode()).hexdigest()[:12]


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return " ".join(str(sanitizar(str(valor))).split())[:LIMITE_TEXTO]


def _data(valor: Any) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _decimal(valor: Any) -> Decimal | None:
    if valor is None or isinstance(valor, bool) or valor == "":
        return None
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


def _inteiro(valor: Any) -> int | None:
    if isinstance(valor, bool) or valor in (None, ""):
        return None
    try:
        return int(str(valor).strip())
    except ValueError:
        return None


def validar_pagina(resposta: Any, pagina: int) -> tuple[list[dict[str, Any]], int, int]:
    """Valida o envelope do Dados Abertos: `(registros, totalRegistros, totalPaginas)`."""
    if not isinstance(resposta, dict):
        raise ErroValidacao("envelope", "resposta não é um objeto")
    registros = resposta.get("resultado")
    total = resposta.get("totalRegistros")
    paginas = resposta.get("totalPaginas")
    if not isinstance(registros, list) or any(not isinstance(r, dict) for r in registros):
        raise ErroValidacao("envelope", "resultado deve ser lista de objetos")
    if type(total) is not int or type(paginas) is not int or total < 0 or paginas < 0:
        raise ErroValidacao("envelope", "totalRegistros/totalPaginas inválidos")
    if not registros and 1 <= pagina <= paginas:
        raise ErroValidacao("pagina_vazia", f"página {pagina} de {paginas} veio vazia")
    if registros and pagina > paginas:
        raise ErroValidacao("envelope", f"página {pagina} acima do total {paginas}")
    return registros, total, paginas


def validar_contrato(registros: Sequence[Mapping[str, Any]], campos: Iterable[str]) -> None:
    """Falha se um campo obrigatório não aparece em nenhum registro da página."""
    if not registros:
        return
    ausentes = [c for c in campos if not any(c in r for r in registros)]
    if ausentes:
        raise ErroValidacao("contrato", f"campos ausentes na API: {', '.join(ausentes)}")


def mapear_ata(bruto: Mapping[str, Any], hoje: date) -> AtaArp | None:
    """Converte uma ata; `None` descarta (sem identificador ou sem data de fim)."""
    id_origem = _texto(bruto.get("numeroControlePncpAta"))
    fim = _data(bruto.get("dataVigenciaFinal"))
    if not id_origem or fim is None:
        return None
    if abs((fim - hoje).days) > FIM_ANOMALO_DIAS:
        raise ErroValidacao("data_anomala", f"fim de vigência {fim} fora do esperado")
    status = _texto(bruto.get("statusAta"))
    excluida = bruto.get("ataExcluido") is True
    cancelada = "cancelad" in normalizar(status)
    compra = _texto(bruto.get("numeroCompra"))
    ano = _texto(bruto.get("anoCompra"))
    return AtaArp(
        id_origem=id_origem,
        numero=_texto(bruto.get("numeroAtaRegistroPreco")),
        unidade_gerenciadora=_texto(bruto.get("nomeUnidadeGerenciadora")),
        orgao=_texto(bruto.get("nomeOrgao")),
        objeto=_texto(bruto.get("objeto")),
        licitacao=f"{compra}/{ano}" if compra and ano else compra or ano,
        inicio=_data(bruto.get("dataVigenciaInicial")),
        fim=fim,
        status_origem=status,
        vigente_na_origem=not excluida and not cancelada,
        link_origem=_texto(bruto.get("linkAtaPNCP")),
        numero_controle_pncp_compra=_texto(bruto.get("numeroControlePncpCompra")),
        valor_total=_decimal(bruto.get("valorTotal")),
        quantidade_itens=_inteiro(bruto.get("quantidadeItens")),
        atualizado_em=_texto(bruto.get("dataHoraAtualizacao")),
    )


def _chave_item(*campos: str) -> str:
    return hashlib.sha256("\x1f".join(campos).encode()).hexdigest()[:32]


def mapear_item(bruto: Mapping[str, Any]) -> ItemArp | None:
    """Converte um item; `None` descarta item excluído ou sem ata/número."""
    ata_id = _texto(bruto.get("numeroControlePncpAta"))
    numero = _texto(bruto.get("numeroItem"))
    if not ata_id or not numero or bruto.get("itemExcluido") is True:
        return None
    ni = bruto.get("niFornecedor")
    digitos = "".join(c for c in str(ni or "") if c.isdigit())
    tipo_pessoa = "PJ" if len(digitos) == 14 else "PF"
    # CPF completo só existe em memória: a identidade guardada é HMAC e a chave usa o mascarado.
    identidade = identificar_fornecedor(
        {"niFornecedor": ni, "tipoPessoa": tipo_pessoa, "numeroControlePNCP": ata_id}
    )
    ni_mascarado = mascarar_ni(str(ni), tipo_pessoa) if ni else ""
    descricao = _texto(bruto.get("descricaoItem"))
    valor = _decimal(bruto.get("valorUnitario"))
    return ItemArp(
        chave=_chave_item(
            ata_id, numero, _texto(bruto.get("codigoItem")), ni_mascarado or "", descricao
        ),
        ata_id_origem=ata_id,
        id_item=numero,
        descricao=descricao,
        nome_catalogo=_texto(bruto.get("nomePdm")),
        tipo_item=_texto(bruto.get("tipoItem")),
        codigo_catalogo=_inteiro(bruto.get("codigoItem")),
        codigo_pdm=_inteiro(bruto.get("codigoPdm")),
        nome_pdm=_texto(bruto.get("nomePdm")),
        id_fornecedor=identidade,
        fornecedor=_texto(bruto.get("nomeRazaoSocialFornecedor")),
        quantidade=_decimal(bruto.get("quantidadeHomologadaItem")),
        valor_unitario=valor,
        valor_valido=valor is not None and valor > 0,
        quantidade_empenhada=_decimal(bruto.get("quantidadeEmpenhada")),
        maximo_adesao=_decimal(bruto.get("maximoAdesao")),
    )


def e_candidata(objeto: str) -> bool:
    """Generosa (recall primeiro): decide de quais atas buscar os itens (ADR 0020)."""
    return classificar_ata(objeto, ()).is_ti or objeto_ata_tem_sinal_ti(objeto)


def _ti_por_catalogo(item: ItemArp, catalogo: CatalogoTI) -> str | None:
    tipo = normalizar(item.tipo_item)
    if tipo.startswith("material") and item.codigo_pdm in catalogo.pdms:
        return f"catmat70:pdm{item.codigo_pdm}@item"
    if tipo.startswith("servico") and item.codigo_catalogo in catalogo.servicos:
        classe = catalogo.servicos[item.codigo_catalogo]
        return f"catser{classe}:servico{item.codigo_catalogo}@item"
    return None


def decidir_ata(objeto: str, itens: Sequence[ItemArp], catalogo: CatalogoTI) -> Decisao:
    """TI = anexo da IN PRODERJ 05 (objeto e nome do PDM) OU catálogo (CATMAT 70 / CATSER).

    O `motivo_ti` registra qual regra decidiu; o anexo vale primeiro para manter o
    comportamento do SIGA, e o catálogo só acrescenta atas de TI quando a regra do anexo
    não achou sinal algum. Exclusões explícitas do anexo (nobreak, drone) não são revertidas.
    """
    decisao = classificar_ata(objeto, sorted({i.nome_pdm for i in itens if i.nome_pdm}))
    if decisao.is_ti or decisao.motivo != "sem_sinal":
        return decisao
    for item in itens:
        motivo = _ti_por_catalogo(item, catalogo)
        if motivo:
            return Decisao(True, motivo)
    return decisao


__all__ = [
    "CAMPOS_ATA",
    "CAMPOS_ITEM",
    "AtaArp",
    "CatalogoTI",
    "Decisao",
    "ItemArp",
    "decidir_ata",
    "e_candidata",
    "mapear_ata",
    "mapear_item",
    "validar_contrato",
    "validar_pagina",
]
