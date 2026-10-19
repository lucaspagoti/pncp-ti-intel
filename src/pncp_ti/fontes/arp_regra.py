"""Regra de TI do ARP pelo catálogo (R2.1, ADR 0025): PDM central, proporção da compra ou itens.

Os parâmetros ficam em `insumos/regra_ti_arp.json` (versionado, revisado pelo Lucas): uma ata
só vira TI por itens de catálogo se tiver um item de PDM central (notebook, microcomputador,
servidor, switch…), **ou** se pelo menos `limiar_proporcao` dos itens da **compra** for de TI,
**ou** se a própria ata tiver `minimo_itens_ata` itens de TI. O ARP emite uma ata por
fornecedor, então a proporção é da compra (todas as atas dela), e não da ata: um mouse pad
sozinho na ata de um fornecedor de material de expediente não classifica a ata (ADR 0025,
item 7).
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
    minimo_itens_ata: int = 2

    def versao(self) -> str:
        conteudo = repr((self.limiar_proporcao, sorted(self.pdms_centrais), self.minimo_itens_ata))
        return hashlib.sha256(conteudo.encode()).hexdigest()[:12]

    def motivo(
        self, ti_ata: int, ti_compra: int, total_compra: int, tem_central: bool
    ) -> str | None:
        """Por qual caminho a ata passa (`central`, `compraKdeT`, `ataKitens`) ou `None`.

        `total_compra` desconhecido (0) nunca passa por proporção.
        """
        if ti_ata <= 0:
            return None
        if tem_central:
            return "central"
        if total_compra > 0 and ti_compra / total_compra >= self.limiar_proporcao:
            return f"compra{ti_compra}de{total_compra}"
        if ti_ata >= self.minimo_itens_ata:
            return f"ata{ti_ata}itens"
        return None

    def passa(self, ti_ata: int, ti_compra: int, total_compra: int, tem_central: bool) -> bool:
        return self.motivo(ti_ata, ti_compra, total_compra, tem_central) is not None


def carregar_regra(caminho: Path = CAMINHO) -> RegraArp:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        limiar = float(dados["limiar_proporcao"])
        centrais = frozenset(int(p["codigo"]) for p in dados["pdms_centrais"])
        minimo = dados["minimo_itens_ata"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ErroValidacao("regra", f"{caminho.name} inválida ({type(exc).__name__})") from exc
    if not 0 < limiar <= 1:
        raise ErroValidacao("regra", "limiar_proporcao deve estar em (0, 1]")
    if isinstance(minimo, bool) or not isinstance(minimo, int) or minimo < 1:
        raise ErroValidacao("regra", "minimo_itens_ata deve ser inteiro >= 1")
    return RegraArp(limiar, centrais, minimo)


REGRA_PADRAO = carregar_regra()
