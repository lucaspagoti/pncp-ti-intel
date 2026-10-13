"""Camada 1 do filtro de TI (ADR 0006): regra determinística por código de
catálogo CATMAT/CATSER e, só na ausência de código, por palavra-chave.

Os códigos abaixo foram confirmados por chamada real ao Dados Abertos
(`/modulo-material/1_consultarGrupoMaterial`, `/modulo-material/2_consultarClasseMaterial`,
`/modulo-servico/4_consultarClasseServico`) nesta sessão (12/10/2026), não
inventados:

- CATMAT grupo 70 — "INFORMÁTICA - EQUIPAMENTOS, PEÇAS, ACESSÓRIOS E
  SUPRIMENTOS DE TIC": todas as 16 classes do grupo são equipamento/suprimento
  de informática (computadores, impressoras, redes, peças) — grupo inteiro é
  seguro de tratar como TI.
- CATSER: não há um único grupo/seção equivalente que cubra só e todo TI sem
  falso positivo (ex.: a classe 8713 "manutenção de equipamento de
  informática" está dentro do grupo 871 "manutenção de produtos de metal",
  que também cobre coisas não-TI). Por isso a lista é por **classe**, não por
  grupo/seção.
- Deliberadamente **fora** da lista confiante: telefonia fixa/móvel/satelital
  (classes 1411-1414, 8411-8417) e acesso à internet (8421-8422). Se isso é
  "TI" pro escopo do Lucas é uma decisão de negócio, não um fato do catálogo —
  cai em INDEFINIDO e a amostra rotulada decide.
- `itemCategoriaIdPncp`/`itemCategoriaNome` do payload (ex.: "Informática
  (TIC)") **não é usado aqui**: medido nesta sessão em ~700 itens reais de
  janelas/datas bem diferentes (material elétrico, ar-condicionado, pasta de
  escritório, cirúrgico) e o valor voltou sempre "(3, 'Informática (TIC)')" —
  parece quebrado/default no Dados Abertos, não uma classificação real por
  item. Não confiar nele.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Any

CATMAT_GRUPO_TI = 70

CATSER_CLASSES_TI = frozenset(
    {
        1111,
        1112,  # desenvolvimento/manutenção de software
        1121,  # manutenção e sustentação de software
        1131,  # documentação de software
        1141,  # engenharia de requisitos de software
        1151,  # mensuração de software
        1161,  # qualidade de software
        1171,  # implementação ágil de software
        1313,  # SaaS
        1611,  # instalação/configuração/customização de software
        1621,  # gerenciamento em TIC
        1631,  # hospedagem em TIC
        1641,  # integração de sistemas em TIC
        1651,  # infraestrutura de TIC (não classificados em outros tópicos)
        1681,
        1682,  # auxiliares de TIC / digitalização-OCR
        1741,  # projetos em TIC
        1821,  # licenciamento de programas de computador
        7331,  # licença de direito de uso de software
        8314,  # consultoria em informática
        8315,  # gerência/gestão em instalações de informática
        8713,  # manutenção e reparo de equipamento de informática
    }
)

_PALAVRAS_TI = (
    "software",
    "licenca de uso",
    "antivirus",
    "firewall",
    "data center",
    "datacenter",
    "computacao em nuvem",
    "saas",
    "notebook",
    "desktop",
    "microcomputador",
    "servidor de rede",
    "servidor de dados",
    "outsourcing de impressao",
    "impressora",
    "rede de computadores",
    "sistema operacional",
    "backup de dados",
    "armazenamento de dados",
    "banco de dados",
    "infraestrutura de ti",
    "tecnologia da informacao",
    "switch de rede",
    "roteador",
    "storage",
)

# Busca de recall alto para o objeto agregado de uma ata. A amostra dos itens
# rejeitados permite revisar falsos negativos e ajustar essa lista.
_PALAVRAS_TI_ATA = _PALAVRAS_TI + (
    "informatica",
    "microinformatica",
    "tecnologia da informacao",
    "tecnologia de informacao",
    "tecnologia da comunicacao",
    "equipamento de informatica",
    "equipamentos de informatica",
    "material de informatica",
    "materiais de informatica",
    "computador",
    "computadores",
    "solucao de tic",
    "solucoes de tic",
    "tic",
    "servico de tic",
    "servicos de tic",
    "telefonia",
    "telecomunicacao",
    "internet",
    "rede de dados",
    "infraestrutura de rede",
)


CATSER_CLASSES_PENDENTES = frozenset({1411, 1412, 1413, 1414, *range(8411, 8418), 8421, 8422})


class PredicaoTI(StrEnum):
    TI = "TI"
    NAO_TI = "NAO_TI"
    INDEFINIDO = "INDEFINIDO"


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _tem_palavra_ti(descricao: str) -> bool:
    texto = _sem_acento(descricao.lower())
    return any(re.search(rf"\b{re.escape(p)}", texto) for p in _PALAVRAS_TI)


def objeto_ata_tem_sinal_ti(descricao: str | None) -> bool:
    """Filtro generoso para o texto agregado de uma ata (ADR 0015).

    Falsos positivos são revisados nas atas candidatas; falsos negativos são
    estimados pela amostra aleatória das atas descartadas.
    """
    if not descricao:
        return False
    texto = _sem_acento(descricao.lower())
    return any(re.search(rf"\b{re.escape(p)}", texto) for p in _PALAVRAS_TI_ATA)


def classificar_por_regra(item: dict[str, Any]) -> PredicaoTI:
    """`item`: linha de `itens_contratacao` (dict com `codigo_item_catalogo`,
    `codigo_grupo`, `codigo_classe`, `material_ou_servico`, `descricao_resumida`,
    `descricao_detalhada`).

    Ordem de decisão (ADR 0006 — código de catálogo primeiro, palavra-chave só
    na ausência de decisão por código): catálogo decide (TI ou NAO_TI) sem
    olhar descrição, mas só quando o campo específico que a decisão depende
    está presente — `codigo_grupo` pra material, `codigo_classe` pra serviço.

    Achado da revisão: antes bastava QUALQUER campo de catálogo não-nulo
    (inclusive só `codigo_item_catalogo`) pra tratar o catálogo como
    "conhecido" e cair direto em NAO_TI — um item com `codigo_item_catalogo`
    preenchido mas `codigo_grupo`/`codigo_classe` nulo (ou `material_ou_servico`
    ausente/corrompido, lacuna de qualidade de dado real já documentada nesta
    base) virava NAO_TI com confiança mesmo podendo ser TI de verdade, e nunca
    passava pela palavra-chave nem caía em INDEFINIDO pra entrar no estrato
    certo da amostra. Agora só decide por catálogo quando o par
    material/campo correspondente está completo; caso contrário cai pra
    palavra-chave como se não houvesse catálogo nenhum.
    """
    codigo_grupo = item.get("codigo_grupo")
    codigo_classe = item.get("codigo_classe")
    material = item.get("material_ou_servico")

    if material == "M" and type(codigo_grupo) is int and codigo_grupo > 0:
        return PredicaoTI.TI if codigo_grupo == CATMAT_GRUPO_TI else PredicaoTI.NAO_TI
    if material == "S" and type(codigo_classe) is int and codigo_classe > 0:
        if codigo_classe in CATSER_CLASSES_PENDENTES:
            return PredicaoTI.INDEFINIDO
        return PredicaoTI.TI if codigo_classe in CATSER_CLASSES_TI else PredicaoTI.NAO_TI

    descricao = " ".join(
        filter(None, (item.get("descricao_resumida"), item.get("descricao_detalhada")))
    )
    if descricao and _tem_palavra_ti(descricao):
        return PredicaoTI.TI
    return PredicaoTI.INDEFINIDO
