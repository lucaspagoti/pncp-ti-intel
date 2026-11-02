"""Juiz da avaliação da busca (ADR 0036): cabeça do item, plural e relatório."""

from pncp_ti import busca_avaliacao as av


def test_cabeca_e_casa():
    assert av._cabeca("MONITOR COMPUTADOR, 24 POL", "") == "MONITOR COMPUTADOR"
    assert av._cabeca("Cabo HDMI - 2 metros", None) == "Cabo HDMI"
    assert av._cabeca("x, y", "MICROCOMPUTADOR") == "MICROCOMPUTADOR"
    assert av._casa("Monitores LED", ["monitor"])
    assert not av._casa("Videomonitoramento", ["monitor"])
    assert av._casa("FONE OUVIDO", ["headset", "fone ouvido"])
    assert not av._casa("Licença Adobe", ["licença Microsoft"])


def test_relatorio_compara_antes_e_depois():
    linha = {"fonte": "compras_arp", "id_ata": "A", "objeto": "Monitores | 24", "relevante": True}
    errada = {**linha, "relevante": False}
    texto = av.relatorio({"monitor": [linha] * 10}, {"monitor": [errada] * 10})
    assert "| monitor | 0% | 100% |" in texto and "Monitores / 24" in texto
