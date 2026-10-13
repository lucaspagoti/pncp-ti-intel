"""Regra de TI baseada no Anexo Único da IN PRODERJ/PRE nº 05/2024 (ADR 0019).

O anexo é rol **exemplificativo** (art. 1º, §1º): a regra só cobre os exemplos
citados e o que for textualmente equivalente. O que ficar fora vira `sem_sinal`
e é revisado na rotulagem, não "descoberto" por palavra-chave mais larga.

Cada termo é uma expressão regular aplicada a texto sem acento e em minúsculas,
com fronteira de palavra. Termos ambíguos ficam ancorados (ex.: `monitor` só
vale como nome de catálogo "monitor" ou "monitor de vídeo", para não casar
"monitor multiparamétrico"). Só o **nome de catálogo** do item (texto antes do
primeiro " - ") e o objeto da ata são lidos; a especificação do item não, porque
é onde aparecem menções incidentais ("... SOFTWARE: ...").

Decisão do Lucas (13/10/2026, depois de ver o conflito): **seguir o anexo**. Telefonia/voz/
internet (I-a), pontos de rede lógicos e elétricos (VIII-a) e videomonitoramento/reconhecimento
facial/LPR (VII-a) são TI. `CATEGORIAS_FORA_DE_ESCOPO` fica vazio e o mecanismo é mantido para
uma futura exclusão pontual. Nobreak e drone não constam do anexo e seguem excluídos pelo objeto
(`TERMOS_FORA_DO_ANEXO`); o que o anexo não lista nem equivale a algo listado fica `sem_sinal`.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

CATEGORIAS: dict[str, tuple[str, ...]] = {
    # I) Segurança e redes
    "I-seguranca": (
        r"firewall",
        r"\bwaf\b",
        r"ciberseguranca",
        r"antivirus",
        r"antispam",
        r"\bendpoint\b",
        r"(prevencao|deteccao) de intrusao",
        r"seguranca da informacao",
        r"teste de intrusao",
        r"\bpentest",
        r"gestao de vulnerabilidades",
        r"tratamento de incidentes",
        r"\bsecaas\b",
        r"monitoria de eventos de seguranca",
        r"centro de operacoes de seguranca",
        r"chaves? criptograficas?",
        r"certificado digital",
        r"certificacao digital",
        r"threat intelligence",
    ),
    "I-redes": (
        r"\bswitch(es)?\b",
        r"\broteador(es)?\b",
        r"equipamentos? wireless",
        r"\bwi-?fi\b",
        r"\bwlan\b",
        r"\brepetidor(es)? de sinal\b",
        r"\bredes? (lan|man|wan)\b",
        r"\binternet das coisas\b",
        r"\biot\b",
    ),
    # I-a: serviço de comunicação de dados, voz, telefonia, internet
    "I-telecom": (
        r"telefonia",
        r"\bvoip\b",
        r"\bvoz\b",
        r"\binternet\b",
        r"comunicacao de dados",
        r"link de dados",
        r"contact center",
        r"\bcall ?center\b",
        r"central telefonica",
        r"\bpabx\b",
    ),
    # II) Infraestrutura de hardware e data center
    "II-infra": (
        r"data ?center",
        r"\bservidor(es)? (fisico|de rede|de dados|de aplicacao|blade|rack|baremetal)",
        r"\bbaremetal\b",
        r"\bblade\b",
        r"hiperconvergencia",
        r"\bstorage\b",
        r"fitoteca",
        r"biblioteca de fita",
        r"appliances?( de backup)?\b",
        r"sala cofre",
        r"\brack seguro\b",
        r"chassi rack",
        r"container dc",
    ),
    "II-software-infra": (
        r"virtualizacao",
        r"\bbackup\b",
        r"monitoramento de rede",
        r"digitalizacao e microfilmagem",
        r"criptografia",
        r"anonimizacao",
        r"cofre de senhas",
        r"banco de dados",
    ),
    # III) Computadores e periféricos
    "III-computadores": (
        r"\bdesktops?\b",
        r"\bnotebooks?\b",
        r"\bmicrocomputador(es)?\b",
        r"\bcomputador(es)?\b",
        r"\btablets?\b",
        r"\bsmartphones?\b",
        r"^monitor( lcd| led| de video| de computador| para computador)?$",
        r"\bmonitores? (lcd|led|de video|de computador|para computador)\b",
        # "filme ... impressora unitarizadora" é insumo de embalagem hospitalar, não impressão de TI
        r"\bimpressoras?\b(?! unitarizadora)",
        r"outsourcing de impressao",
        r"equipamentos? de informatica",
        r"materiais? de informatica",
        r"\bmicroinformatica\b",
    ),
    # IV) Nuvem
    "IV-nuvem": (
        r"\b(iaas|paas|saas|dbaas|daas|caas|faas|bdaas)\b",
        r"computacao em nuvem",
        r"\bnuvem\b",
        r"\bcloud\b",
        r"multi-?nuvem",
        r"(infraestrutura|plataforma|software) como servico",
    ),
    # V) Hospedagem
    "V-hospedagem": (
        r"\bcolocation\b",
        r"\bhosting\b",
        r"hospedagem",
    ),
    # VI) Desenvolvimento de software e licenciamentos
    "VI-software": (
        r"\bsoftwares?\b",
        r"licencas? de (uso de )?softwares?",
        r"licenciamento de (software|programas?)",
        r"subscricao de software",
        r"desenvolvimento de (sistemas?|aplicativos?|websites?)",
        r"\bwebsites?\b",
        r"\bwebservice\b",
        r"\bapi\b",
        r"barramento",
        r"solucoes? sistemicas?",
        r"\bdevops\b",
        r"fabrica de software",
        r"\bchatbot\b",
        r"\bbpm\b",
        r"\bintranet\b",
        r"business intelligence",
        r"inteligencia de negocios",
        r"inteligencia analitica",
        r"inteligencia artificial",
        r"machine learning",
        r"\berp\b",
        r"gestao de ativos",
        r"aplicativos? moveis?",
        r"sistema operacional",
    ),
    # VII) Soluções de vídeo
    "VII-video": (
        r"videoconferencia",
        r"tela interativa",
        r"sala inteligente",
        r"telepresenca",
    ),
    # VII-a: videomonitoramento, reconhecimento facial, LPR
    "VII-videomonitoramento": (
        r"videomonitoramento",
        r"\bcftv\b",
        r"reconhecimento facial",
        r"\blpr\b",
        r"leitura de placas",
    ),
    # VIII) Suporte
    "VIII-suporte": (
        r"suporte tecnico de microinformatica",
        r"suporte (de campo|a usuarios de (tic|ti))",
        r"service desk",
        r"central de servicos de (tic|ti)",
        r"atendimento a requisicoes de suporte",
    ),
    # VIII-a: pontos de rede lógicos e elétricos, infraestrutura de rede
    "VIII-rede-fisica": (
        r"pontos? (logicos?|de rede)",
        r"cabeamento",
        r"fibra optica",
        r"infraestrutura de rede",
        r"rede estruturada",
    ),
    # Termos gerais de TIC
    "geral": (
        r"tecnologia da informacao",
        r"tecnologia de informacao",
        r"tecnologia da informacao e comunicacao",
        r"\btic\b",
        r"informatica",
        r"\bhardware\b",
        r"\bti\b",
    ),
}

# Categorias do anexo que o projeto exclui por decisão própria. Vazio: segue o anexo (ADR 0019).
CATEGORIAS_FORA_DE_ESCOPO: frozenset[str] = frozenset()

# Não constam do anexo; excluídos pelo Lucas. Valem só para o OBJETO da ata (itens de software
# dentro de uma ata de drones ou nobreaks não tornam a ata de TI).
TERMOS_FORA_DO_ANEXO: tuple[str, ...] = (
    r"\bno-?breaks?\b",
    r"\bdrones?\b",
)

_COMPILADOS = {
    categoria: tuple(re.compile(termo) for termo in termos)
    for categoria, termos in CATEGORIAS.items()
}
_FORA_DO_ANEXO = tuple(re.compile(t) for t in TERMOS_FORA_DO_ANEXO)


def versao_regra() -> str:
    """Hash do conteúdo da regra; vai para `cargas.geracao` para detectar carga defasada."""
    conteudo = repr((CATEGORIAS, sorted(CATEGORIAS_FORA_DE_ESCOPO), TERMOS_FORA_DO_ANEXO))
    return hashlib.sha256(conteudo.encode()).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class Decisao:
    is_ti: bool
    motivo: str


def normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.lower().split())


def nome_de_catalogo(descricao: str) -> str:
    """O SIGA descreve itens como `NOME DO CATÁLOGO - ATRIBUTO: valor`."""
    return descricao.split(" - ", 1)[0].strip()


def _primeiro_sinal(texto: str, ignorar: frozenset[str] = frozenset()) -> tuple[str, str] | None:
    for categoria, padroes in _COMPILADOS.items():
        if categoria in ignorar:
            continue
        for padrao in padroes:
            achado = padrao.search(texto)
            if achado:
                return categoria, achado.group(0)
    return None


def classificar_ata(objeto: str, nomes_catalogo: Iterable[str]) -> Decisao:
    """Decide se uma ata é de TI, e devolve o motivo (auditável na rotulagem).

    Ordem: (1) sinal de TI dentro do escopo no objeto inclui; (2) termo fora do anexo no
    objeto exclui (mesmo com item de TI); (3) sinal de TI nos nomes de catálogo inclui;
    (4) sinal só em categoria fora do escopo exclui, com o motivo; (5) sem sinal.
    """
    texto_objeto = normalizar(objeto)
    # Objeto que cita TI e também nobreak/drone ("microcomputadores e nobreaks") segue como TI.
    sinal_objeto = _primeiro_sinal(texto_objeto, ignorar=CATEGORIAS_FORA_DE_ESCOPO)
    if sinal_objeto:
        return Decisao(True, f"{sinal_objeto[0]}:{sinal_objeto[1]}@objeto")
    for padrao in _FORA_DO_ANEXO:
        achado = padrao.search(texto_objeto)
        if achado:
            return Decisao(False, f"excluido:fora_do_anexo:{achado.group(0)}")

    nomes = [normalizar(n) for n in nomes_catalogo]
    fontes = [("objeto", texto_objeto), *(("item", n) for n in nomes)]

    for origem, texto in fontes:
        sinal = _primeiro_sinal(texto, ignorar=CATEGORIAS_FORA_DE_ESCOPO)
        if sinal:
            return Decisao(True, f"{sinal[0]}:{sinal[1]}@{origem}")
    for origem, texto in fontes:
        sinal = _primeiro_sinal(texto)
        if sinal:
            return Decisao(False, f"excluido:fora_de_escopo:{sinal[0]}:{sinal[1]}@{origem}")
    return Decisao(False, "sem_sinal")
