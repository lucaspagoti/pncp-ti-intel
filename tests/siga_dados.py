"""CSVs sintéticos do SIGA RJ (cp1252, `;`), gerados em bytes para os testes.

Nenhum dado real: nomes, processos e valores são inventados. O CPF da fixture é
fictício e existe só para provar o mascaramento.
"""

from __future__ import annotations

from pncp_ti.fontes.siga_csv import CABECALHO_ATAS, CABECALHO_ITENS, CABECALHO_PARTICIPANTES

GERACAO = "13/10/2026"
CPF_FICTICIO = "12345678909"


def _csv(cabecalho: tuple[str, ...], linhas: list[list[str]]) -> bytes:
    def campo(c: str) -> str:
        return c

    texto = "\r\n".join(
        [";".join([f'"{cabecalho[0]}"', *cabecalho[1:]])]
        + [";".join(campo(c) for c in linha) for linha in linhas]
    )
    return (texto + "\r\n").encode("cp1252")


def ata(
    id_ata: str,
    objeto: str,
    *,
    status: str = "Válida",
    inicio: str = "01/01/2026",
    fim: str = "31/12/2099",
    processo: str | None = None,
    geracao: str = GERACAO,
) -> list[str]:
    processo = processo or f"E-01/{int(id_ata):03d}/2026"
    return [
        id_ata, f"{int(id_ata):04d}/2026", "UNIDADE  TESTE ", objeto, "PE 001/26   ",
        inicio, fim, "Menor Preço", "Não", status, "10", f"9{id_ata}", processo, geracao,
    ]  # fmt: skip


def item(
    id_ata: str,
    id_item: str,
    descricao: str,
    *,
    fornecedor: str = "ACME TECNOLOGIA LTDA",
    id_forn: str = "5",
    qtd: str = "100",
    valor: str = "12,50",
    geracao: str = GERACAO,
) -> list[str]:
    return [
        id_ata, f"{int(id_ata):04d}/2026/1-01", "Menor Preço", id_item, descricao,
        id_forn, fornecedor, qtd, valor, "", geracao,
    ]  # fmt: skip


def participante(
    id_ata: str,
    id_item: str,
    unidade: str = "SEPLAG - SUBSECRETARIA",
    *,
    demandada: str = "100",
    consumida: str = "120",
    geracao: str = GERACAO,
) -> list[str]:
    return [
        id_ata, f"{int(id_ata):04d}/2026/1-01", unidade, "Menor Preço", "ITEM TESTE",
        id_item, demandada, consumida, "1000,00", "1200,00", geracao,
    ]  # fmt: skip


def conjunto_basico(geracao: str = GERACAO) -> tuple[bytes, bytes, bytes]:
    """7 atas (1 com 2 processos). TI + Válida + vigentes: 1, 4, 6 (CFTV) e 7 (VOIP)."""
    atas = [
        ata("1", "OUTSOURCING DE IMPRESSÃO", geracao=geracao),
        ata("1", "OUTSOURCING DE IMPRESSÃO", processo="E-01/901/2026", geracao=geracao),
        ata("2", "MEDICAMENTO", geracao=geracao),
        ata("3", "LICENCIAMENTO DE SOFTWARE", status="Interrompida", geracao=geracao),
        ata("4", "AQUISIÇÃO DE NOTEBOOKS", inicio="", geracao=geracao),
        ata("5", "SOFTWARE DE BACKUP", fim="01/01/2026", geracao=geracao),
        ata("6", "CATRACA - CFTV", geracao=geracao),
        ata("7", "VOIP", geracao=geracao),
    ]
    impressao = item(
        "1", "11", "SERVICO DE LOCACAO DE EQUIPAMENTO DE INFORMATICA - DESCRIÇÃO: IMPRESSORA A4",
        geracao=geracao,
    )  # fmt: skip
    itens = [
        impressao,
        list(impressao),  # linha idêntica (efeito dos processos repetidos)
        item(
            "1", "11", impressao[4], qtd="50", valor="11,90", geracao=geracao
        ),  # mesma chave, outro valor
        item("1", "12", "TONER - TIPO: PRETO", valor="", geracao=geracao),
        item(
            "4",
            "13",
            "NOTEBOOK - TIPO: 14 POLEGADAS",
            fornecedor=f"JOSE DA SILVA {CPF_FICTICIO}",
            id_forn="6",
            qtd="10",
            valor="4.500,00",
            geracao=geracao,
        ),  # fmt: skip
        item("4", "14", "NOTEBOOK - TIPO: 15 POLEGADAS", valor="0,00", geracao=geracao),
        item("2", "21", "DIPIRONA - 500MG", geracao=geracao),
        item("6", "61", "CATRACA - TIPO: PEDESTAL", geracao=geracao),
    ]
    part = [
        participante("1", "11", geracao=geracao),
        participante("1", "11", geracao=geracao),  # idêntica
        participante("1", "11", "SES - SECRETARIA", demandada="10", consumida="2", geracao=geracao),
        participante("4", "13", geracao=geracao),
    ]
    return (
        _csv(CABECALHO_ATAS, atas),
        _csv(CABECALHO_ITENS, itens),
        _csv(CABECALHO_PARTICIPANTES, part),
    )


def conjunto_grande(n_atas: int, geracao: str = GERACAO) -> tuple[bytes, bytes, bytes]:
    """`n_atas` atas não-TI, cada uma com 1 item e 1 participante (testes de limiar)."""
    atas = [ata(str(i), "MEDICAMENTO", geracao=geracao) for i in range(1, n_atas + 1)]
    itens = [
        item(str(i), str(1000 + i), "DIPIRONA - 500MG", geracao=geracao)
        for i in range(1, n_atas + 1)
    ]
    part = [participante(str(i), str(1000 + i), geracao=geracao) for i in range(1, n_atas + 1)]
    return (
        _csv(CABECALHO_ATAS, atas),
        _csv(CABECALHO_ITENS, itens),
        _csv(CABECALHO_PARTICIPANTES, part),
    )


def com_orfaos(base: tuple[bytes, bytes, bytes], n: int) -> tuple[bytes, bytes, bytes]:
    extra = "".join(
        ";".join(item("99999", str(9000 + i), "ORFAO - X")) + "\r\n" for i in range(n)
    ).encode("cp1252")
    return base[0], base[1] + extra, base[2]


def escrever(diretorio, conjunto: tuple[bytes, bytes, bytes]) -> None:
    from pncp_ti.fontes.siga import ARQUIVOS

    for nome, conteudo in zip(("atas", "itens", "participantes"), conjunto, strict=True):
        (diretorio / ARQUIVOS[nome]).write_bytes(conteudo)
