"""Relatório da auditoria ARP: texto de terceiros mascarado."""

from datetime import date, timedelta

import pytest

from pncp_ti.fontes.arp_auditoria import _celula, no_universo

HOJE = date(2026, 10, 14)


def test_celula_mascara_cpf_e_escapa_barra_vertical():
    texto = _celula("TONER | fornecedor 12345678909")
    assert "12345678909" not in texto
    assert "|" not in texto


@pytest.mark.parametrize(
    ("vigente", "inicio", "fim", "esperado"),
    [
        (True, HOJE - timedelta(days=10), HOJE + timedelta(days=10), True),
        (True, None, HOJE, True),
        (True, HOJE + timedelta(days=1), HOJE + timedelta(days=90), False),  # começa amanhã
        (True, HOJE - timedelta(days=90), HOJE - timedelta(days=1), False),  # venceu ontem
        (False, HOJE - timedelta(days=10), HOJE + timedelta(days=10), False),  # cancelada
    ],
)
def test_universo_da_auditoria_e_o_mesmo_da_view(vigente, inicio, fim, esperado):
    ata = {"vigente_na_origem": vigente, "inicio": inicio, "fim": fim}
    assert no_universo(ata, HOJE) is esperado
