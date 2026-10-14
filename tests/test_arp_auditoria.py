"""Relatório da auditoria ARP: texto de terceiros mascarado."""

from pncp_ti.fontes.arp_auditoria import _celula


def test_celula_mascara_cpf_e_escapa_barra_vertical():
    texto = _celula("TONER | fornecedor 12345678909")
    assert "12345678909" not in texto
    assert "|" not in texto
