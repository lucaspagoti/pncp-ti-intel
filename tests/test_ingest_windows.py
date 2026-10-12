"""Testes de `pncp_ti.ingest.windows` — sem rede, sem banco."""

from datetime import date, timedelta

import pytest

from pncp_ti.ingest.windows import gerar_janelas


def test_janela_unica_quando_intervalo_cabe_no_limite():
    janelas = gerar_janelas(date(2026, 1, 1), date(2026, 1, 10), max_dias=30)
    assert len(janelas) == 1
    assert janelas[0].inicio == date(2026, 1, 1)
    assert janelas[0].fim == date(2026, 1, 10)


def test_janelas_cobrem_o_intervalo_sem_buraco_e_sem_sobreposicao():
    desde, ate = date(2023, 4, 1), date(2026, 10, 12)
    janelas = gerar_janelas(desde, ate, max_dias=365)

    assert janelas[0].inicio == desde
    assert janelas[-1].fim == ate
    for i in range(len(janelas) - 1):
        assert janelas[i + 1].inicio == janelas[i].fim + timedelta(days=1)
    for janela in janelas:
        assert janela.inicio <= janela.fim
        assert (janela.fim - janela.inicio).days < 365


def test_janela_respeita_max_dias():
    janelas = gerar_janelas(date(2026, 1, 1), date(2026, 1, 1), max_dias=1)
    assert len(janelas) == 1
    assert janelas[0].inicio == janelas[0].fim == date(2026, 1, 1)


def test_desde_depois_de_ate_levanta_erro():
    with pytest.raises(ValueError):
        gerar_janelas(date(2026, 1, 10), date(2026, 1, 1))
