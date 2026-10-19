"""Dados sintéticos da web (R4), compartilhados por `test_web.py` e pelos E2E (`tests/e2e/`).

Nenhum dado real. `comandos()` devolve os INSERTs como (sql, parâmetros), para rodar tanto em
conexão async (testes com `TestClient`) quanto síncrona (servidor do E2E).
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

FIM = date.today() + timedelta(days=60)
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


def item(carga, ata_id, n, descricao, valor, fornecedor="ACME") -> Comando:
    return (
        "INSERT INTO ata_itens (carga_id, chave, ata_id_origem, id_item, descricao, nome_catalogo, "
        "fornecedor, quantidade, valor_unitario, valor_valido) "
        "VALUES (%s, %s, %s, %s, %s, '', %s, 10, %s, true)",
        (carga, f"{ata_id}-{n}", ata_id, str(n), descricao, fornecedor, valor),
    )


def comandos(siga: UUID | None = None, arp: UUID | None = None) -> list[Comando]:
    """Cargas ativas do SIGA e do ARP com três atas, itens e um participante."""
    siga, arp = siga or uuid4(), arp or uuid4()
    cargas = [
        (
            "INSERT INTO cargas (id, fonte, data_referencia, status, ativa) "
            "VALUES (%s, %s, %s, 'concluida', true)",
            (carga, fonte, date.today()),
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
            fim=date.today() + timedelta(days=5),
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
