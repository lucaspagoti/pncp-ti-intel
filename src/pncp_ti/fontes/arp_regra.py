"""Regra de TI do ARP pelo catálogo (R2.1, ADR 0025): proporção de itens ou PDM central.

Os parâmetros ficam em `insumos/regra_ti_arp.json` (versionado, revisado pelo Lucas): uma ata
só vira TI por itens de catálogo se pelo menos `limiar_proporcao` dos itens for de TI **ou**
se tiver um item de PDM central (notebook, microcomputador, servidor, switch…). Item de TI
incidental (mouse pad numa ata de EPI) não classifica a ata.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pncp_ti.fontes.siga_csv import ErroValidacao

CAMINHO = Path(__file__).resolve().parents[3] / "insumos" / "regra_ti_arp.json"


@dataclass(frozen=True, slots=True)
class RegraArp:
    limiar_proporcao: float
    pdms_centrais: frozenset[int]

    def versao(self) -> str:
        conteudo = repr((self.limiar_proporcao, sorted(self.pdms_centrais)))
        return hashlib.sha256(conteudo.encode()).hexdigest()[:12]

    def passa(self, itens_ti: int, itens_total: int, tem_central: bool) -> bool:
        """`itens_total` desconhecido (0) só passa pelo PDM central, nunca por proporção."""
        if tem_central:
            return itens_ti > 0
        return itens_total > 0 and itens_ti / itens_total >= self.limiar_proporcao


def carregar_regra(caminho: Path = CAMINHO) -> RegraArp:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        limiar = float(dados["limiar_proporcao"])
        centrais = frozenset(int(p["codigo"]) for p in dados["pdms_centrais"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ErroValidacao("regra", f"{caminho.name} inválida ({type(exc).__name__})") from exc
    if not 0 < limiar <= 1:
        raise ErroValidacao("regra", "limiar_proporcao deve estar em (0, 1]")
    return RegraArp(limiar, centrais)


REGRA_PADRAO = carregar_regra()
