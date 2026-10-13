"""Exporta o censo de atas vigentes para rotulagem manual de TI (ADR 0019).

O SIGA tem poucas atas vigentes (~1,5 mil), então a rotulagem cobre **todas** (censo)
e dispensa amostragem. O CSV leva a decisão do sistema, a pré-rotulagem (preenchida
fora daqui, com o critério citado) e a coluna final `rotulo_lucas`.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

import psycopg

from pncp_ti.config import get_settings
from pncp_ti.db import conectar

CABECALHO = [
    "fonte",
    "id_ata",
    "numero",
    "unidade_gerenciadora",
    "objeto",
    "nomes_catalogo",
    "status_origem",
    "vigencia_fim",
    "filtro_sistema",
    "motivo_sistema",
    "rotulo_pre",
    "criterio_pre",
    "rotulo_lucas",
    "observacao",
]
CAMINHO_SAIDA = Path(__file__).resolve().parents[3] / "insumos" / "rotulagem_siga.csv"
NOMES_POR_ATA = 8
TEXTOS_EXTERNOS = {
    "id_ata",
    "numero",
    "unidade_gerenciadora",
    "objeto",
    "nomes_catalogo",
    "motivo_sistema",
    "criterio_pre",
    "observacao",
}

_HOJE_SP = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"


async def gerar_censo(
    conn: psycopg.AsyncConnection, fonte: str = "siga_rj"
) -> list[dict[str, str]]:
    """Todas as atas da carga ativa com status `Válida` e vigência cobrindo hoje."""
    cursor = await conn.execute(
        f"""
        SELECT c.fonte, a.id_origem, a.numero, a.unidade_gerenciadora, a.objeto,
               a.status_origem, a.fim, a.is_ti, a.motivo_ti,
               (SELECT string_agg(nome, ' | ' ORDER BY nome) FROM (
                    SELECT DISTINCT i.nome_catalogo AS nome FROM ata_itens i
                    WHERE i.carga_id = a.carga_id AND i.ata_id_origem = a.id_origem
                    ORDER BY 1 LIMIT {NOMES_POR_ATA}) n) AS nomes
        FROM atas a
        JOIN cargas c ON c.id = a.carga_id AND c.ativa AND c.status = 'concluida'
        WHERE c.fonte = %s AND a.status_origem = 'Válida'
          AND (a.inicio IS NULL OR a.inicio <= {_HOJE_SP}) AND a.fim >= {_HOJE_SP}
        ORDER BY length(a.id_origem), a.id_origem
        """,
        (fonte,),
    )
    return [
        {
            "fonte": linha["fonte"],
            "id_ata": linha["id_origem"],
            "numero": linha["numero"],
            "unidade_gerenciadora": linha["unidade_gerenciadora"] or "",
            "objeto": linha["objeto"],
            "nomes_catalogo": linha["nomes"] or "",
            "status_origem": linha["status_origem"],
            "vigencia_fim": str(linha["fim"] or ""),
            "filtro_sistema": "TI" if linha["is_ti"] else "NAO_TI",
            "motivo_sistema": linha["motivo_ti"] or "",
            "rotulo_pre": "",
            "criterio_pre": "",
            "rotulo_lucas": "",
            "observacao": "",
        }
        for linha in await cursor.fetchall()
    ]


def escrever_csv(linhas: list[dict[str, str]], caminho: Path = CAMINHO_SAIDA) -> None:
    with caminho.open("x", newline="", encoding="utf-8") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=CABECALHO)
        writer.writeheader()
        for linha in linhas:
            # Aspas do formato CSV não impedem planilhas de executar fórmulas.
            # Neutralizar somente texto externo; os demais campos ficam como estão.
            writer.writerow(
                {
                    campo: "'" + valor
                    if campo in TEXTOS_EXTERNOS
                    and (
                        valor.startswith(("\t", "\r", "\n"))
                        or valor.lstrip().startswith(("=", "+", "-", "@"))
                    )
                    else valor
                    for campo, valor in linha.items()
                }
            )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Censo de atas vigentes do SIGA para rotulagem; não sobrescreve arquivos."
    )
    parser.add_argument("--saida", type=Path, default=CAMINHO_SAIDA)
    args = parser.parse_args()
    if args.saida.exists():
        raise SystemExit("Arquivo já existe. Use --saida com outro nome para preservar os rótulos.")
    conn = await conectar(get_settings())
    try:
        linhas = await gerar_censo(conn)
    finally:
        await conn.close()
    if not linhas:
        raise SystemExit("Não há carga ativa do SIGA; execute `make ingest` primeiro.")
    escrever_csv(linhas, args.saida)
    print(f"{len(linhas)} atas escritas em {args.saida}")


if __name__ == "__main__":
    asyncio.run(main())
