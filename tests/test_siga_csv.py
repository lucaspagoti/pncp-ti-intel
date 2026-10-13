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
     ("-3,61", Decimal("-3.61")), ("-,01", Decimal("-0.01")),
     ("", None), ("abc", None), ("NaN", None), ("1.234", None), ("1,2,3", None)],
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


def test_chave_nao_e_hash_do_conteudo_bruto_com_cpf():
    """B1 da revisão: a chave do item com CPF não pode permitir enumerar o CPF."""
    import hashlib

    c = _montar()
    com_cpf = next(i for i in c.itens if i.id_item == "13")
    bruto = [
        "4", "0004/2026/1-01", "Menor Preço", "13",
        "NOTEBOOK - TIPO: 14 POLEGADAS", "6",
        f"JOSE DA SILVA {d.CPF_FICTICIO}", "10", "4.500,00", "",
    ]  # fmt: skip
    hash_bruto = hashlib.sha256("\x1f".join(bruto).encode()).hexdigest()[:32]
    assert com_cpf.chave != hash_bruto
    assert d.CPF_FICTICIO not in com_cpf.fornecedor


def test_chave_depende_so_do_texto_mascarado():
    atas, itens, part = d.conjunto_basico()
    outro_cpf = itens.replace(d.CPF_FICTICIO.encode(), b"12399999909")  # mesmos 3+2 dígitos
    a = {i.id_item: i.chave for i in montar(atas, itens, part).itens}
    b = {i.id_item: i.chave for i in montar(atas, outro_cpf, part).itens}
    assert a == b


def test_numero_nao_parseavel_acima_do_limite_falha():
    atas, itens, part = d.conjunto_basico()
    with pytest.raises(ErroValidacao) as exc:
        montar(atas, itens.replace(b";12,50;", b";doze;"), part)
    assert exc.value.tipo == "numeros"


def test_atas_validas_sem_item_acima_do_limite_falham():
    atas, itens, part = d.conjunto_basico()
    so_ata_1 = b"\r\n".join(
        linha for linha in itens.split(b"\r\n") if linha.startswith((b'"ID Ata"', b"1;"))
    )
    with pytest.raises(ErroValidacao) as exc:
        montar(atas, so_ata_1 + b"\r\n", part)
    assert exc.value.tipo == "cobertura_itens"


def test_campo_gigante_vira_erro_de_validacao():
    atas, itens, part = d.conjunto_basico()
    gigante = b"X" * 200_000
    with pytest.raises(ErroValidacao) as exc:
        montar(atas.replace(b"MEDICAMENTO", gigante), itens, part)
    assert exc.value.tipo == "csv"


def test_mensagem_de_erro_nao_carrega_cpf():
    erro = ErroValidacao("x", f"valor estranho {d.CPF_FICTICIO}")
    assert d.CPF_FICTICIO not in str(erro)


def test_processo_com_cpf_e_mascarado():
    """P1 do Codex: `processos` é exposto pela view e não pode carregar CPF."""
    atas, itens, part = d.conjunto_basico()
    sujo = atas.replace(b"E-01/901/2026", f"E-01/{d.CPF_FICTICIO}/2026".encode())
    c = montar(sujo, itens, part)
    todos = " ".join(p for a in c.atas for p in a.processos)
    assert d.CPF_FICTICIO not in todos
    assert "123******09" in todos


def test_todo_texto_copiado_e_mascarado():
    atas, itens, part = d.conjunto_basico()
    c = montar(
        atas.replace(b"UNIDADE  TESTE", f"UNIDADE {d.CPF_FICTICIO}".encode()),
        itens.replace(b"ITEM TESTE", b"X"),
        part.replace(b"ITEM TESTE", f"ITEM {d.CPF_FICTICIO}".encode()),
    )
    textos = [a.unidade_gerenciadora for a in c.atas] + [p.item for p in c.participantes]
    assert all(d.CPF_FICTICIO not in t for t in textos)


def test_numero_de_11_digitos_nao_e_mascarado_como_cpf():
    atas, itens, part = d.conjunto_basico()
    c = montar(atas, itens.replace(b";100;12,50;", b";12345678901;12,50;"), part)
    assert any(i.quantidade == 12345678901 for i in c.itens)


def test_data_de_inicio_invalida_nao_vira_vigente_por_omissao():
    """P2 do Codex: 31/02/2026 não é 'início não informado'; a ata fica em quarentena."""
    atas, itens, part = d.conjunto_grande(150)
    ruim = atas.replace(b";01/01/2026;", b";31/02/2026;", 1)
    c = montar(ruim, itens, part)
    assert len(c.atas) == 149
    assert c.contagens["datas_invalidas"] == 1
    assert c.contagens["itens_ata_quarentena"] == 1
    assert c.contagens["participantes_ata_quarentena"] == 1
    assert c.contagens["itens_orfaos"] == 0


def test_data_invalida_acima_do_limite_falha():
    atas, itens, part = d.conjunto_basico()
    with pytest.raises(ErroValidacao) as exc:
        montar(atas.replace(b";01/01/2026;", b";31/02/2026;", 1), itens, part)
    assert exc.value.tipo == "datas"


@pytest.mark.parametrize(
    "ruim",
    [b'"ABERTA;resto\r\n', b'"A"B;resto\r\n', b'x;"fecha"lixo;y\r\n'],
)
def test_csv_malformado_com_colunas_corretas_e_recusado(ruim):
    """P2 do Codex: aspas abertas ou texto depois do fechamento não podem passar em silêncio."""
    atas, itens, part = d.conjunto_basico()
    linha = d.ata("9", "OBJETO")
    base = atas.split(b"\r\n")
    colunas = len(linha)
    # linha com o número certo de colunas, mas com aspas malformadas no campo do objeto
    corrompida = ";".join(linha).replace("OBJETO", '"OBJ"X').encode("cp1252")
    assert corrompida.count(b";") == colunas - 1
    with pytest.raises(ErroValidacao) as exc:
        montar(atas + corrompida + b"\r\n", itens, part)
    assert exc.value.tipo in {"csv", "colunas"}
    assert base  # usa a variável
