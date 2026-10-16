"""Unidades explícitas derivadas na view, sem converter valores ou inventar duração."""

from decimal import Decimal

import psycopg
import pytest
import siga_dados as d

from pncp_ti.fontes.siga import arquivos_de_diretorio, carregar


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Licença/mês", "licença/mês"),
        ("LICENÇA POR MÊS", "licença/mês"),
        ("Licença mensal", "licença/mês"),
        ("Licenças mensais", "licença/mês"),
        ("Usuário/ano", "usuário/ano"),
        ("Usuários por ano", "usuário/ano"),
        ("Página impressa A4", "página impressa"),
        ("PÁGINAS IMPRESSAS", "página impressa"),
        ("Licença anual", None),
        ("Licença por 36 meses", None),
        ("Impressora com 500 páginas de manual", None),
        ("Franquia mensal de 10.000 páginas impressas", None),
        ("Pacote de 100 licenças/mês", None),
        ("Licença/mês com instalação de 10 usuários/ano", None),
        ("Licença/mês ou usuário/ano", None),
        ("Notebook", None),
        (None, None),
    ],
)
async def test_unidade_conservadora(conn_ingest, texto, esperado):
    row = await (
        await conn_ingest.execute("SELECT unidade_preco_ti(%s) AS unidade", (texto,))
    ).fetchone()
    assert row["unidade"] == esperado


async def test_view_preserva_preco_e_leitor_nao_escreve(conn_ingest, conn_reader, tmp_path):
    d.escrever(tmp_path, d.conjunto_basico())
    await carregar(conn_ingest, arquivos_de_diretorio(tmp_path))
    await conn_ingest.execute(
        "UPDATE ata_itens SET descricao='Licença/mês', valor_unitario=120, valor_valido=true "
        "WHERE ata_id_origem='1'"
    )
    await conn_ingest.commit()
    linhas = await (
        await conn_reader.execute("SELECT * FROM v_ata_precos_ti WHERE id_ata='1'")
    ).fetchall()
    assert linhas
    assert all(r["preco_por_unidade"] == r["valor_unitario"] == Decimal(120) for r in linhas)
    assert all(r["unidade_preco"] == "licença/mês" for r in linhas)
    await conn_reader.commit()
    for comando in (
        "SELECT * FROM notificacoes",
        "SELECT * FROM digest_atas",
        "UPDATE ata_itens SET valor_unitario=1",
        "SELECT * FROM atas_vistas",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn_reader.execute(comando)
        await conn_reader.rollback()
