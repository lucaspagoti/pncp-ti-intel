"""Dados sintéticos da web (R4), compartilhados por `test_web.py` e pelos E2E (`tests/e2e/`).

Nenhum dado real. `comandos()` devolve os INSERTs como (sql, parâmetros), para rodar tanto em
conexão async (testes com `TestClient`) quanto síncrona (servidor do E2E).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from pncp_ti.web.consultas import hoje

# O dia de Brasília, como a web calcula: `date.today()` é UTC no CI e erra das 21h à meia-noite.
HOJE = hoje()
FIM = HOJE + timedelta(days=60)
# Objeto com fórmula: a exportação CSV precisa neutralizá-lo.
OBJETO_FORMULA = '=HYPERLINK("http://x") toner'
Comando = tuple[str, tuple]


def ata(carga, fonte_id, objeto, *, fim=FIM, orgao="ORGAO X", uf=None, esfera=None) -> Comando:
    return (
        "INSERT INTO atas (carga_id, id_origem, numero, objeto, orgao, status_origem, is_ti, "
        "vigente_na_origem, fim, uf, esfera, link_origem) "
        "VALUES (%s, %s, '1/2026', %s, %s, 'Válida', true, true, %s, %s, %s, %s)",
        (carga, fonte_id, objeto, orgao, fim, uf, esfera, "https://pncp.gov.br/app/atas/1"),
    )


def ata_proderj(carga, id_origem, objeto, processo, *, fim=FIM) -> Comando:
    """Ata do SIGA gerenciada pelo PRODERJ, com o processo SEI que casa com o site (ADR 0042)."""
    return (
        "INSERT INTO atas (carga_id, id_origem, numero, objeto, unidade_gerenciadora, "
        "status_origem, is_ti, vigente_na_origem, fim, processos) "
        "VALUES (%s, %s, '1/2026/403200-01', %s, "
        "'PRODERJ - CENTRO DE TECN DE INFORMAÇÃO E COMUN DO ERJ', 'Válida', true, true, %s, %s)",
        (carga, id_origem, objeto, fim, [processo] if processo else []),
    )


def item(carga, ata_id, n, descricao, valor, fornecedor="ACME", catalogo="") -> Comando:
    return (
        "INSERT INTO ata_itens (carga_id, chave, ata_id_origem, id_item, descricao, nome_catalogo, "
        "fornecedor, quantidade, valor_unitario, valor_valido) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 10, %s, true)",
        (carga, f"{ata_id}-{n}", ata_id, str(n), descricao, catalogo, fornecedor, valor),
    )


REFRESH: Comando = ("SELECT atualizar_busca()", ())  # a web lê a busca materializada (0010)


def comandos(siga: UUID | None = None, arp: UUID | None = None) -> list[Comando]:
    """Cargas ativas do SIGA e do ARP com três atas, itens e um participante."""
    siga, arp = siga or uuid4(), arp or uuid4()
    cargas = [
        (
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
            "VALUES (%s, %s, %s, 'concluida', true)",
            (carga, fonte, HOJE),
        )
        for carga, fonte in ((siga, "siga_rj"), (arp, "compras_arp"))
    ]
    return [
        *cargas,
        ata(siga, "S1", "Aquisição de notebooks para a rede estadual"),
        item(siga, "S1", 1, "Notebook 16GB", 4500),
        item(siga, "S1", 2, "Mouse óptico", 30),
        ata(arp, "A1", "Outsourcing de impressão departamental", orgao="MINISTERIO"),
        item(arp, "A1", 1, "Impressão A4 monocromática", 0.12),
        ata(
            arp,
            "A2",
            "<script>alert(1)</script> licença Microsoft",
            fim=HOJE + timedelta(days=5),
            uf="SP",
            esfera="Municipal",
        ),
        (
            "INSERT INTO ata_participantes (carga_id, chave, ata_id_origem, id_item, item, "
            "unidade, qtd_demandada, qtd_consumida) "
            "VALUES (%s, 'p1', 'S1', '1', 'Notebook', 'SEFAZ', 5, 2)",
            (siga,),
        ),
    ]
