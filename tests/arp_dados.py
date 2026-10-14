"""Respostas sintéticas do Dados Abertos (módulo ARP) para os testes.

Nenhum dado real: nomes, órgãos e valores são inventados. O CPF da fixture é fictício e
existe só para provar o mascaramento.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

CPF_FICTICIO = "12345678909"
CNPJ_FICTICIO = "11222333000181"


def hoje() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def ata(
    numero: str,
    objeto: str,
    *,
    fim: date | None = None,
    inicio: date | None = None,
    status: str = "Ata de Registro de Preços",
    excluida: bool = False,
    atualizado: str = "2026-10-01T10:00:00",
    assinatura: date | None = None,
) -> dict[str, Any]:
    fim = fim or hoje() + timedelta(days=90)
    inicio = inicio or hoje() - timedelta(days=30)
    return {
        "numeroAtaRegistroPreco": f"{numero}/2026",
        "codigoUnidadeGerenciadora": "999999",
        "nomeUnidadeGerenciadora": "UNIDADE TESTE",
        "nomeOrgao": "ORGAO TESTE   ",
        "linkAtaPNCP": f"https://pncp.gov.br/app/atas/00000000000191/2026/{numero}/1",
        "numeroCompra": "00010",
        "anoCompra": "2026",
        "dataAssinatura": (assinatura or inicio).isoformat(),
        "dataVigenciaInicial": inicio.isoformat(),
        "dataVigenciaFinal": fim.isoformat(),
        "valorTotal": 1000.0,
        "statusAta": status,
        "objeto": objeto,
        "quantidadeItens": 2,
        "dataHoraAtualizacao": atualizado,
        "ataExcluido": excluida,
        "numeroControlePncpAta": f"00000000000191-1-{numero}/2026-000001",
        "numeroControlePncpCompra": f"00000000000191-1-{numero}/2026",
    }


def id_ata(numero: str) -> str:
    return f"00000000000191-1-{numero}/2026-000001"


def item(
    numero_ata: str,
    numero_item: str,
    descricao: str,
    *,
    tipo: str = "Material",
    codigo: int = 1000,
    pdm: int | None = 500,
    nome_pdm: str = "PRODUTO",
    ni: str = CNPJ_FICTICIO,
    valor: float = 12.5,
    excluido: bool = False,
) -> dict[str, Any]:
    return {
        "numeroAtaRegistroPreco": f"{numero_ata}/2026",
        "numeroItem": numero_item,
        "codigoItem": codigo,
        "descricaoItem": descricao,
        "tipoItem": tipo,
        "quantidadeHomologadaItem": 10.0,
        "niFornecedor": ni,
        "nomeRazaoSocialFornecedor": "ACME TECNOLOGIA LTDA",
        "valorUnitario": valor,
        "maximoAdesao": 20.0,
        "quantidadeEmpenhada": 1.0,
        "itemExcluido": excluido,
        "numeroControlePncpAta": id_ata(numero_ata),
        "codigoPdm": pdm,
        "nomePdm": nome_pdm,
    }


def envelope(registros: list[dict[str, Any]], *, total: int | None = None, paginas: int = 1):
    return {
        "resultado": registros,
        "totalRegistros": len(registros) if total is None else total,
        "totalPaginas": paginas,
        "paginasRestantes": 0,
    }


class ClienteFalso:
    """Imita `DadosAbertosClient.list_resource` com páginas e itens pré-montados.

    Reproduz o defeito real da paginação: cada página repete o último registro da anterior,
    então uma janela com mais de uma página perde registros no fim.
    """

    def __init__(
        self,
        atas: list[dict[str, Any]],
        itens: dict[str, list[dict[str, Any]]],
        pdms: list[int] | None = None,
        servicos: dict[int, int] | None = None,
        *,
        tamanho: int = 500,
    ) -> None:
        self.atas = atas
        self.itens = itens
        self.pdms = pdms if pdms is not None else [239, 283]
        self.servicos = servicos if servicos is not None else {1260: 8713}
        self.tamanho = tamanho
        self.chamadas: list[str] = []
        self.filtros: list[tuple[str, dict[str, Any]]] = []
        self.lote: list[dict[str, Any]] = []  # itens do endpoint em lote (2_consultarARPItem)

    def _fatiar(self, registros: list[dict[str, Any]], pagina: int):
        paginas = max(1, -(-len(registros) // self.tamanho)) if registros else 0
        inicio = (pagina - 1) * (self.tamanho - 1)
        return envelope(
            registros[inicio : inicio + self.tamanho], total=len(registros), paginas=paginas
        )

    async def list_resource(self, rota: str, *, pagina: int = 1, tamanho_pagina: int = 50, **f):
        self.chamadas.append(rota)
        self.filtros.append((rota, f))
        if rota.endswith("1.2_consultarARP_FimVigencia"):
            minimo = f["dataVigenciaFinalMin"]
            maximo = f["dataVigenciaFinalMax"]
            do_periodo = [a for a in self.atas if minimo <= a["dataVigenciaFinal"] <= maximo]
            if "dataAssinaturaInicial" in f:
                do_periodo = [
                    a
                    for a in do_periodo
                    if f["dataAssinaturaInicial"] <= a["dataAssinatura"] <= f["dataAssinaturaFinal"]
                ]
            return self._fatiar(do_periodo, pagina)
        if rota.endswith("2_consultarARPItem"):
            do_grupo = [
                i
                for i in self.lote
                if i["codigoUnidadeGerenciadora"] == f["codigoUnidadeGerenciadora"]
                and i["numeroCompra"] == f["numeroCompra"]
                and f["dataVigenciaInicialMin"]
                <= i["dataVigenciaInicial"]
                <= f["dataVigenciaInicialMax"]
            ]
            return self._fatiar(do_grupo, pagina)
        if rota.endswith("2.1_consultarARPItem_Id"):
            return self._fatiar(self.itens.get(f["numeroControlePncpAta"], []), pagina)
        if rota.endswith("3_consultarPdmMaterial"):
            return self._fatiar([{"codigoPdm": p} for p in self.pdms], pagina)
        if rota.endswith("6_consultarItemServico"):
            registros = [
                {"codigoServico": s, "codigoClasse": c}
                for s, c in self.servicos.items()
                if c == f["codigoClasse"]
            ]
            return self._fatiar(registros, pagina)
        raise AssertionError(f"rota inesperada: {rota}")

    def buscadas(self) -> list[str]:
        """Atas cujos itens foram buscados por id."""
        return [f["numeroControlePncpAta"] for r, f in self.filtros if r.endswith("Item_Id")]
