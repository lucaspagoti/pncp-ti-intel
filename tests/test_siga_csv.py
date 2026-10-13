"""Parse e validação dos CSVs do SIGA RJ (sem banco, sem rede)."""

from datetime import date
from decimal import Decimal

import pytest
import siga_dados as d

from pncp_ti.fontes import siga_csv
from pncp_ti.fontes.siga_csv import ErroValidacao, decodificar, montar


def _montar(conjunto=None):
    return montar(*(conjunto or d.conjunto_basico()))


def test_ata_com_dois_processos_vira_uma_ata_com_os_dois_processos():
    c = _montar()
    por_id = {a.id_origem: a for a in c.atas}
    assert len(c.atas) == 7
    assert por_id["1"].processos == ("E-01/001/2026", "E-01/901/2026")
    assert c.contagens["linhas_atas"] == 8
    assert c.contagens["atas_multiprocesso"] == 1
    assert c.contagens["atas_conflito"] == 0


def test_linha_identica_e_deduplicada_mas_valor_diferente_e_preservado():
    c = _montar()
    da_ata_1 = [i for i in c.itens if i.ata_id_origem == "1" and i.id_item == "11"]
    assert sorted(i.valor_unitario for i in da_ata_1) == [Decimal("11.90"), Decimal("12.50")]
    assert c.contagens["itens_duplicados"] == 1
    assert c.contagens["participantes_duplicados"] == 1


def test_chave_e_estavel_entre_execucoes():
    assert {i.chave for i in _montar().itens} == {i.chave for i in _montar().itens}
    assert len({i.chave for i in _montar().itens}) == len(_montar().itens)


def test_valor_vazio_ou_nao_positivo_nao_vira_preco():
    c = _montar()
    invalidos = {i.id_item: i for i in c.itens if not i.valor_valido}
    assert set(invalidos) == {"12", "14"}
    assert all(i.valor_unitario is None for i in invalidos.values())


def test_decimal_com_milhar_e_virgula():
    c = _montar()
    notebook = next(i for i in c.itens if i.id_item == "13")
    assert notebook.valor_unitario == Decimal("4500.00")
    assert notebook.quantidade == Decimal("10")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("1.234,56", Decimal("1234.56")), (",45", Decimal("0.45")), ("7", Decimal("7")),
     ("", None), ("abc", None), ("NaN", None)],
)  # fmt: skip
def test_decimal(texto, esperado):
    assert siga_csv._decimal(texto) == esperado


def test_inicio_vazio_fica_nulo_e_nao_e_erro():
    c = _montar()
    assert next(a for a in c.atas if a.id_origem == "4").inicio is None
    assert next(a for a in c.atas if a.id_origem == "1").inicio == date(2026, 1, 1)


def test_cpf_em_nome_de_fornecedor_e_mascarado():
    c = _montar()
    nomes = " ".join(i.fornecedor for i in c.itens)
    assert d.CPF_FICTICIO not in nomes
    assert "JOSE DA SILVA 123" in nomes


def test_espacos_internos_sao_normalizados():
    assert next(a for a in _montar().atas if a.id_origem == "1").unidade_gerenciadora == (
        "UNIDADE TESTE"
    )


def test_cabecalho_com_espaco_antes_do_nome_e_aceito():
    atas, itens, part = d.conjunto_basico()
    itens = itens.replace(b";N\xb0 da Ata;", b"; N\xb0 da Ata;")
    assert itens != d.conjunto_basico()[1]
    assert len(montar(atas, itens, part).atas) == 7


def test_cabecalho_trocado_falha():
    atas, itens, part = d.conjunto_basico()
    with pytest.raises(ErroValidacao) as exc:
        montar(atas.replace(b"Status da Ata", b"Situacao"), itens, part)
    assert exc.value.tipo == "cabecalho"


def test_geracoes_diferentes_entre_arquivos_falham():
    atas, itens, _ = d.conjunto_basico()
    _, _, part_antigo = d.conjunto_basico(geracao="12/10/2026")
    with pytest.raises(ErroValidacao) as exc:
        montar(atas, itens, part_antigo)
    assert exc.value.tipo == "geracao"


def test_mais_de_uma_data_extracao_no_mesmo_arquivo_falha():
    atas, itens, part = d.conjunto_basico()
    with pytest.raises(ErroValidacao) as exc:
        montar(atas.replace(b"13/10/2026\r\n", b"12/10/2026\r\n", 1), itens, part)
    assert exc.value.tipo == "geracao"


def test_arquivo_so_com_cabecalho_ou_vazio_falha():
    atas, itens, part = d.conjunto_basico()
    cabecalho = atas.split(b"\r\n", 1)[0] + b"\r\n"
    for ruim in (cabecalho, b""):
        with pytest.raises(ErroValidacao) as exc:
            montar(ruim, itens, part)
        assert exc.value.tipo == "vazio"


def test_linha_truncada_falha_com_numero_de_colunas():
    atas, itens, part = d.conjunto_basico()
    with pytest.raises(ErroValidacao) as exc:
        montar(atas + b"1;0001/2026;SO TRES\r\n", itens, part)
    assert exc.value.tipo == "colunas"


def test_cp1252_decodifica_travessao_e_aspas_tipograficas():
    assert decodificar("ITEM – 3”".encode("cp1252"), "x") == "ITEM – 3”"


def test_utf8_e_rejeitado():
    with pytest.raises(ErroValidacao) as exc:
        decodificar("AÇÃO ÚNICA".encode(), "x")
    assert exc.value.tipo == "codificacao"
    with pytest.raises(ErroValidacao):
        decodificar(b"\xef\xbb\xbfID Ata", "x")


def test_texto_legitimo_com_a_til_nao_e_mojibake():
    assert decodificar("AQUISIÇÃO DE AÇÃO – NÃO".encode("cp1252"), "x").startswith("AQUISIÇÃO")


def test_byte_indefinido_em_cp1252_falha():
    with pytest.raises(ErroValidacao) as exc:
        decodificar(b"abc\x81def", "x")
    assert exc.value.tipo == "codificacao"


def test_orfaos_acima_do_limite_falham():
    with pytest.raises(ErroValidacao) as exc:
        montar(*d.com_orfaos(d.conjunto_basico(), 2))
    assert exc.value.tipo == "orfaos"


def test_orfaos_abaixo_do_limite_sao_descartados_e_contados():
    c = montar(*d.com_orfaos(d.conjunto_grande(150), 1))
    assert c.contagens["itens_orfaos"] == 1
    assert c.contagens["itens_gravados"] == 150
    assert all(i.ata_id_origem != "99999" for i in c.itens)
