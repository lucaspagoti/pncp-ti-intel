"""Geração de janelas de data para a ingestão (ADR 0005 — carga por janelas)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Limite real confirmado por chamada direta ao PNCP nesta sessão (12/10/2026) para
# /v1/contratacoes/publicacao, /v1/atas e /v1/contratos: "Período maior que 365 dias"
# em 422. O comentário do compras-mcp cita ~30 dias para contratações, mas na prática
# o próprio PNCP aceita até 365 — vale reconferir se a API mudar (snapshot de tools
# não cobre limites de endpoint, só nomes/descrições).
MAX_JANELA_DIAS = 365


@dataclass(frozen=True, slots=True)
class Janela:
    inicio: date
    fim: date


def gerar_janelas(desde: date, ate: date, *, max_dias: int = MAX_JANELA_DIAS) -> list[Janela]:
    """Gera janelas contíguas, sem sobreposição e sem buraco, de `desde` até `ate` (inclusive).

    Cada janela tem no máximo `max_dias` dias corridos.
    """
    if max_dias < 1:
        raise ValueError("max_dias deve ser >= 1")
    if desde > ate:
        raise ValueError(f"desde ({desde}) é depois de ate ({ate})")

    janelas: list[Janela] = []
    passo = timedelta(days=max_dias - 1)
    cursor = desde
    while cursor <= ate:
        fim = min(cursor + passo, ate)
        janelas.append(Janela(inicio=cursor, fim=fim))
        cursor = fim + timedelta(days=1)
    return janelas
