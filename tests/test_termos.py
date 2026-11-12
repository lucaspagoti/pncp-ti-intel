"""Termos da busca (ADR 0036): palavra exata com plural, sinônimos e marcação do item."""

from __future__ import annotations

import pytest

from pncp_ti.web import termos


@pytest.mark.parametrize(
    ("palavra", "contem", "nao_contem"),
    [
        ("monitor", {"monitor", "monitores"}, {"monitoramento"}),
        ("monitores", {"monitor"}, set()),
        ("impressora", {"impressoras"}, set()),
        ("licencas", {"licenca"}, set()),
        ("cartao", {"cartoes"}, set()),
        ("cartoes", {"cartao"}, set()),
        ("papel", {"papeis"}, set()),
        ("papeis", {"papel"}, set()),
        ("garagem", {"garagens"}, set()),
        ("2026", {"2026"}, {"2026s"}),
    ],
)
def test_variantes_de_plural(palavra, contem, nao_contem):
    v = termos.variantes(palavra)
    assert contem <= v and not (nao_contem & v)


def test_consulta_exata_so_tem_palavras_e_operadores():
    exata = termos.consulta_exata(["Monitores de vídeo", "'; DROP TABLE atas;--"])
    assert exata == (
        "((monitor | monitores) & (video | videos)) | "
        "((drop | drops) & (table | tables) & (ata | atas))"
    )
    assert termos.consulta_exata(["de da do"]) is None
    assert termos.consulta_exata([]) is None


def test_sinonimos_so_quando_a_busca_e_o_termo_do_grupo():
    assert "computador portátil" in termos.sinonimos("Notebook")
    assert termos.sinonimos("notebook dell") == []
    assert len(termos.sinonimos("notebook")) <= termos.MAX_ALTERNATIVAS


def test_marcar_escapa_e_marca_a_palavra():
    marcado = termos.marcar("MONITOR COMPUTADOR <B>", ["monitores"])
    assert str(marcado) == "<mark>Monitor</mark> computador &lt;b&gt;"
    assert str(termos.marcar("Câmera de videomonitoramento", ["monitor"])) == (
        "Câmera de videomonitoramento"
    )
    assert str(termos.marcar(None, ["x"])) == ""


def test_categorias_do_insumo_sao_validas():
    """O arquivo que o Lucas revisa (ADR 0043): slug único e seguro, rótulo e termos preenchidos."""
    lidas = termos.categorias()
    assert len(lidas) == 8
    assert len({c.slug for c in lidas}) == len(lidas)
    for c in lidas:
        assert c.slug.replace("-", "").isalnum() and c.slug == c.slug.lower()
        assert c.rotulo and c.termos
    assert termos.categoria("rede").rotulo == "Rede e segurança"
    # Ninguém pediu videomonitoramento nem telefonia.
    assert {"videomonitoramento", "telefonia"}.isdisjoint({c.slug for c in lidas})


def test_categoria_fora_da_lista_fechada_vira_nada():
    for slug in ("", "nao-existe", "rede'; DROP TABLE atas;--", "REDE", "rede "):
        assert termos.categoria(slug) is None


def test_categorias_le_o_formato_e_ignora_linha_torta(tmp_path):
    arquivo = tmp_path / "cat.txt"
    arquivo.write_text(
        "# comentário\n"
        "a | Rótulo A | um = dois palavras\n"
        "linha sem barras\n"
        "Maiúscula | Ruim | x\n"  # slug com maiúscula é recusado
        "sem-termos | Vazia |\n"
        "b | Rótulo B | tres # comentário no fim\n",
        encoding="utf-8",
    )
    termos.categorias.cache_clear()
    try:
        lidas = termos.categorias(arquivo)
    finally:
        termos.categorias.cache_clear()
    assert [(c.slug, c.rotulo, c.termos) for c in lidas] == [
        ("a", "Rótulo A", ("um", "dois palavras")),
        ("b", "Rótulo B", ("tres",)),
    ]
