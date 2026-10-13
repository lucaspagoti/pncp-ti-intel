"""Leitura, validação e normalização dos 3 CSVs do SIGA RJ (ADR 0019).

Sem I/O de rede nem de banco: recebe bytes, devolve registros tipados. Tudo o que
pode estar errado na origem falha alto (`ErroValidacao`) em vez de publicar uma
carga incoerente.

Formato observado em 13/10/2026: `cp1252` (há travessão e aspas tipográficas nos
itens; latin-1 as decodificaria como controle), separador `;`, decimal com vírgula,
datas `dd/mm/aaaa`. O `ID Ata` repete em `atas` (uma linha por processo SEI) e esse
efeito se propaga como linhas idênticas em itens e participantes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pncp_ti.privacy import sanitizar

CABECALHO_ATAS = (
    "ID Ata",
    "Número da Ata",
    "Unidade Gerenciadora",
    "Objeto",
    "Licitação",
    "Início da Validade",
    "Fim da Validade",
    "Critério de Julgamento",
    "Cont. Tempo de Serviço",
    "Status da Ata",
    "id licitacao",
    "id processo",
    "processo",
    "data_extracao",
)
CABECALHO_ITENS = (
    "ID Ata",
    "N° da Ata",
    "Critério de Julgamento",
    "ID Item",
    "Item",
    "ID Forn",
    "Fornecedor",
    "Qtd",
    "Vl. Unitário",
    "Taxa %",
    "data_extracao",
)
CABECALHO_PARTICIPANTES = (
    "ID Ata",
    "N° da Ata",
    "Unid. Participante",
    "Critério de Julgamento",
    "Item",
    "id item",
    "Qtd Demandada",
    "Qtd Consumida",
    "Valor Demandado",
    "Valor Consumido",
    "data_extracao",
)

LIMITE_ORFAOS = 0.01
LIMITE_CONFLITOS = 0.01
LIMITE_SEM_ITEM = 0.05
# UTF-8 lido como cp1252 vira "Ã©", "Âº" etc.; em português legítimo "Ã" só precede letras.
_MOJIBAKE = re.compile("Ã[©§£¡³ªº¢´µ¨ƒ‡°]|Â[ºª°]")


class ErroValidacao(RuntimeError):
    """Falha de validação da origem; `tipo` é estável e vai para `cargas.erro_tipo`."""

    def __init__(self, tipo: str, mensagem: str) -> None:
        # Mensagens vão para log e para `cargas`; texto de origem passa por `sanitizar`.
        super().__init__(str(sanitizar(mensagem))[:300])
        self.tipo = tipo


@dataclass(frozen=True, slots=True)
class Ata:
    id_origem: str
    numero: str
    unidade_gerenciadora: str
    objeto: str
    licitacao: str
    inicio: date | None
    fim: date | None
    criterio_julgamento: str
    status_origem: str
    processos: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Item:
    chave: str
    ata_id_origem: str
    id_item: str
    descricao: str
    nome_catalogo: str
    id_fornecedor: str
    fornecedor: str
    quantidade: Decimal | None
    valor_unitario: Decimal | None
    taxa_pct: Decimal | None
    valor_valido: bool


@dataclass(frozen=True, slots=True)
class Participante:
    chave: str
    ata_id_origem: str
    id_item: str
    item: str
    unidade: str
    qtd_demandada: Decimal | None
    qtd_consumida: Decimal | None
    valor_demandado: Decimal | None
    valor_consumido: Decimal | None


@dataclass(slots=True)
class ConjuntoSiga:
    data_extracao: date
    atas: list[Ata]
    itens: list[Item]
    participantes: list[Participante]
    contagens: dict[str, int] = field(default_factory=dict)


def decodificar(conteudo: bytes, nome: str) -> str:
    """cp1252 estrito: byte indefinido ou sinal de UTF-8 indica mudança na origem."""
    if conteudo.startswith(b"\xef\xbb\xbf"):
        raise ErroValidacao("codificacao", f"{nome}: BOM UTF-8; a origem mudou de codificação")
    try:
        texto = conteudo.decode("cp1252")
    except UnicodeDecodeError as exc:
        raise ErroValidacao("codificacao", f"{nome}: byte inválido em cp1252: {exc}") from None
    if _MOJIBAKE.search(texto):
        raise ErroValidacao("codificacao", f"{nome}: sequência típica de UTF-8 lido como cp1252")
    return texto


def _normalizar(valor: str) -> str:
    return " ".join(valor.split())


def _ler_tabela(
    texto: str, esperado: tuple[str, ...], nome: str, numericas: tuple[int, ...]
) -> list[list[str]]:
    """Lê o CSV em modo estrito e mascara CPF em toda célula de texto.

    `numericas` (e a última coluna, `data_extracao`) ficam como vieram: um número de 11
    dígitos não é CPF e perderia o valor. Todo o resto passa por `sanitizar` aqui, então
    nenhum campo copiado adiante (ids, processos, números) escapa do mascaramento.
    """
    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=";", quotechar='"', strict=True)
    try:
        cabecalho = [c.strip() for c in next(leitor)]
    except StopIteration:
        raise ErroValidacao("vazio", f"{nome}: arquivo vazio") from None
    except csv.Error as exc:
        raise ErroValidacao("csv", f"{nome}: CSV malformado no cabeçalho: {exc}") from None
    if tuple(cabecalho) != esperado:
        raise ErroValidacao("cabecalho", f"{nome}: cabeçalho inesperado: {cabecalho!r}")
    linhas: list[list[str]] = []
    try:
        for numero, linha in enumerate(leitor, start=2):
            if not linha:
                continue
            if len(linha) != len(esperado):
                raise ErroValidacao(
                    "colunas",
                    f"{nome}: linha {numero} com {len(linha)} colunas, esperado {len(esperado)}",
                )
            linhas.append(
                [
                    _normalizar(c) if i in numericas or i == len(linha) - 1 else _texto(c)
                    for i, c in enumerate(linha)
                ]
            )
    except csv.Error as exc:
        raise ErroValidacao("csv", f"{nome}: CSV malformado: {exc}") from None
    if not linhas:
        raise ErroValidacao("vazio", f"{nome}: sem linhas de dados")
    return linhas


def _data_extracao(linhas: list[list[str]], nome: str) -> date:
    valores = {linha[-1] for linha in linhas}
    if len(valores) != 1:
        raise ErroValidacao("geracao", f"{nome}: data_extracao com mais de um valor: {valores!r}")
    data = _data(next(iter(valores)))
    if data is None:
        raise ErroValidacao("geracao", f"{nome}: data_extracao inválida")
    return data


def _data(valor: str) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError:
        return None


# Formatos aceitos (com `-` opcional): `12`, `12,50`, `,45` e `4.500,00`. Ponto sem vírgula
# (`1.234`) é ambíguo entre milhar e decimal e vira inválido, em vez de arriscar um erro de
# 1000x em silêncio.
_NUMERO = re.compile(r"^-?(?:\d+(?:,\d+)?|,\d+|\d{1,3}(?:\.\d{3})+,\d+)$")


def _decimal(valor: str) -> Decimal | None:
    if not valor or not _NUMERO.match(valor):
        return None
    try:
        return Decimal(valor.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _invalidos(linha: list[str], colunas: tuple[int, ...]) -> bool:
    """Há número não vazio que não parseia?"""
    return any(linha[c] and _decimal(linha[c]) is None for c in colunas)


def _chave(*campos: str) -> str:
    return hashlib.sha256("\x1f".join(campos).encode()).hexdigest()[:32]


def _texto(valor: str) -> str:
    """Normaliza e mascara CPF em texto de terceiros."""
    return _normalizar(sanitizar(valor))


def montar(
    conteudo_atas: bytes, conteudo_itens: bytes, conteudo_participantes: bytes
) -> ConjuntoSiga:
    linhas_atas = _ler_tabela(
        decodificar(conteudo_atas, "ATA_REGISTRO_PRECO"),
        CABECALHO_ATAS,
        "ATA_REGISTRO_PRECO",
        (),
    )
    linhas_itens = _ler_tabela(
        decodificar(conteudo_itens, "ITENS_ATAS_REGISTRO_PRECO"),
        CABECALHO_ITENS,
        "ITENS_ATAS_REGISTRO_PRECO",
        (7, 8, 9),
    )
    linhas_part = _ler_tabela(
        decodificar(conteudo_participantes, "PARTICIPANTES_ATAS_REGISTRO_PRECO"),
        CABECALHO_PARTICIPANTES,
        "PARTICIPANTES_ATAS_REGISTRO_PRECO",
        (6, 7, 8, 9),
    )

    datas = {
        _data_extracao(linhas_atas, "ATA_REGISTRO_PRECO"),
        _data_extracao(linhas_itens, "ITENS_ATAS_REGISTRO_PRECO"),
        _data_extracao(linhas_part, "PARTICIPANTES_ATAS_REGISTRO_PRECO"),
    }
    if len(datas) != 1:
        raise ErroValidacao(
            "geracao", f"arquivos de gerações diferentes (data_extracao): {sorted(datas)!r}"
        )
    data_extracao = datas.pop()

    contagens: dict[str, int] = {"linhas_atas": len(linhas_atas)}

    # --- atas: uma linha por processo; colapsa por ID Ata ---
    por_id: dict[str, list[list[str]]] = defaultdict(list)
    for linha in linhas_atas:
        por_id[linha[0]].append(linha)
    atas: list[Ata] = []
    quarentena: set[str] = set()  # ata com data de vigência preenchida e inválida
    conflitos = multiprocesso = 0
    for id_origem, grupo in sorted(por_id.items()):
        grupo.sort(key=lambda linha: (linha[12], linha[11]))
        base = grupo[0]
        # Colunas de negócio (todas exceto `id processo` e `processo`) devem coincidir.
        if any(g[:11] != base[:11] or g[13] != base[13] for g in grupo[1:]):
            conflitos += 1
        if len(grupo) > 1:
            multiprocesso += 1
        inicio, fim = _data(base[5]), _data(base[6])
        # Vazio é "não informado" (aceito); preenchido e inválido NÃO vira vigente por omissão.
        if (inicio is None and base[5]) or (fim is None and base[6]):
            quarentena.add(id_origem)
            continue
        processos = tuple(sorted({g[12] for g in grupo if g[12]}))
        atas.append(
            Ata(
                id_origem=id_origem,
                numero=_texto(base[1]),
                unidade_gerenciadora=_texto(base[2]),
                objeto=_texto(base[3]),
                licitacao=_texto(base[4]),
                inicio=inicio,
                fim=fim,
                criterio_julgamento=_texto(base[7]),
                status_origem=_texto(base[9]),
                processos=processos,
            )
        )
    contagens.update(
        atas_unicas=len(atas),
        atas_multiprocesso=multiprocesso,
        atas_conflito=conflitos,
        datas_invalidas=len(quarentena),
    )
    if len(quarentena) > LIMITE_CONFLITOS * len(por_id):
        raise ErroValidacao("datas", f"{len(quarentena)} atas com data de vigência inválida")
    if conflitos > LIMITE_CONFLITOS * len(por_id):
        raise ErroValidacao(
            "conflito_ata", f"{conflitos} atas com campos divergentes entre linhas do mesmo ID"
        )
    ids = {a.id_origem for a in atas}

    # --- itens: dedupe por conteúdo; chave estável ---
    itens: dict[str, Item] = {}
    orfaos_itens = invalidos = numeros_invalidos = itens_quarentena = 0
    for linha in linhas_itens:
        if linha[0] in quarentena:
            itens_quarentena += 1
            continue
        if linha[0] not in ids:
            orfaos_itens += 1
            continue
        descricao = _texto(linha[4])
        fornecedor = _texto(linha[6])
        valor = _decimal(linha[8])
        valido = valor is not None and valor > 0
        # A chave usa o texto já mascarado: nunca o CPF completo (ADR 0013 e 0019).
        chave = _chave(
            linha[0], _texto(linha[1]), _texto(linha[2]), linha[3], descricao, linha[5],
            fornecedor, linha[7], linha[8], linha[9],
        )  # fmt: skip
        if chave in itens:
            continue
        numeros_invalidos += _invalidos(linha, (7, 8, 9))
        invalidos += not valido
        itens[chave] = Item(
            chave=chave,
            ata_id_origem=linha[0],
            id_item=linha[3],
            descricao=descricao,
            nome_catalogo=descricao.split(" - ", 1)[0].strip(),
            id_fornecedor=linha[5],
            fornecedor=fornecedor,
            quantidade=_decimal(linha[7]),
            valor_unitario=valor if valido else None,
            taxa_pct=_decimal(linha[9]),
            valor_valido=valido,
        )
    contagens.update(
        linhas_itens=len(linhas_itens),
        itens_orfaos=orfaos_itens,
        itens_ata_quarentena=itens_quarentena,
        itens_gravados=len(itens),
        itens_duplicados=len(linhas_itens) - orfaos_itens - itens_quarentena - len(itens),
        itens_valor_invalido=invalidos,
        itens_numero_invalido=numeros_invalidos,
    )
    if orfaos_itens > LIMITE_ORFAOS * len(linhas_itens):
        raise ErroValidacao("orfaos", f"{orfaos_itens} itens sem ata correspondente")
    if numeros_invalidos > LIMITE_CONFLITOS * len(itens):
        raise ErroValidacao("numeros", f"{numeros_invalidos} itens com número não parseável")

    # Cobertura: um arquivo de itens regenerado pela metade deixaria atas válidas sem preço.
    com_item = {i.ata_id_origem for i in itens.values()}
    validas = [a.id_origem for a in atas if a.status_origem == "Válida"]
    sem_item = sum(1 for id_ in validas if id_ not in com_item)
    contagens["validas_sem_item"] = sem_item
    if validas and sem_item > LIMITE_SEM_ITEM * len(validas):
        raise ErroValidacao(
            "cobertura_itens", f"{sem_item} de {len(validas)} atas válidas sem nenhum item"
        )

    # --- participantes ---
    participantes: dict[str, Participante] = {}
    orfaos_part = part_numeros_invalidos = part_quarentena = 0
    for linha in linhas_part:
        if linha[0] in quarentena:
            part_quarentena += 1
            continue
        if linha[0] not in ids:
            orfaos_part += 1
            continue
        item_texto, unidade = _texto(linha[4]), _texto(linha[2])
        chave = _chave(
            linha[0], _texto(linha[1]), unidade, _texto(linha[3]), item_texto, linha[5],
            linha[6], linha[7], linha[8], linha[9],
        )  # fmt: skip
        if chave in participantes:
            continue
        part_numeros_invalidos += _invalidos(linha, (6, 7, 8, 9))
        participantes[chave] = Participante(
            chave=chave,
            ata_id_origem=linha[0],
            id_item=linha[5],
            item=item_texto,
            unidade=unidade,
            qtd_demandada=_decimal(linha[6]),
            qtd_consumida=_decimal(linha[7]),
            valor_demandado=_decimal(linha[8]),
            valor_consumido=_decimal(linha[9]),
        )
    contagens.update(
        linhas_participantes=len(linhas_part),
        participantes_orfaos=orfaos_part,
        participantes_gravados=len(participantes),
        participantes_ata_quarentena=part_quarentena,
        participantes_duplicados=len(linhas_part)
        - orfaos_part
        - part_quarentena
        - len(participantes),
        participantes_numero_invalido=part_numeros_invalidos,
    )
    if part_numeros_invalidos > LIMITE_CONFLITOS * len(participantes):
        raise ErroValidacao(
            "numeros", f"{part_numeros_invalidos} participantes com número não parseável"
        )
    if orfaos_part > LIMITE_ORFAOS * len(linhas_part):
        raise ErroValidacao("orfaos", f"{orfaos_part} participantes sem ata correspondente")

    return ConjuntoSiga(
        data_extracao=data_extracao,
        atas=atas,
        itens=list(itens.values()),
        participantes=list(participantes.values()),
        contagens=contagens,
    )
