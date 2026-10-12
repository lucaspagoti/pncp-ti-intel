"""Sinalização de falhas e atualização diária sem rede ou banco."""

from argparse import Namespace
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock

import pytest

from pncp_ti.ingest import cli, contratacoes
from pncp_ti.ingest.executar import FalhasIngestao
from pncp_ti.ingest.windows import Janela


def test_cli_sai_com_erro_sem_expor_mensagem(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "_parse_args", lambda: Namespace(entidades="contratacoes", diario=True, forcar=False)
    )
    monkeypatch.setattr(cli, "_rodar", AsyncMock(side_effect=ValueError("CPF 12345678901")))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert "12345678901" not in output.out + output.err


async def test_diario_consulta_publicacao_e_atualizacao(monkeypatch):
    executar = AsyncMock()
    monkeypatch.setattr(contratacoes, "ingerir_janela", executar)
    monkeypatch.setattr(contratacoes, "MODALIDADES_PNCP", [{"codigo": 6}])
    await contratacoes.ingerir(
        None, None, None, Janela(date(2026, 10, 1), date(2026, 10, 2)), atualizacoes=True
    )
    calls = executar.call_args_list
    assert [c.kwargs["path"] for c in calls] == [
        "/v1/contratacoes/publicacao",
        "/v1/contratacoes/atualizacao",
    ]
    assert len({c.kwargs["entidade"] for c in calls}) == 2


async def test_falha_item_continua_proximas_entidades(monkeypatch):
    conn = AsyncMock()
    monkeypatch.setattr(cli, "conectar", AsyncMock(return_value=conn))

    @asynccontextmanager
    async def cliente():
        yield object()

    monkeypatch.setattr(cli, "criar_cliente", cliente)
    ruim = AsyncMock(side_effect=FalhasIngestao(2))
    bom = AsyncMock()
    monkeypatch.setattr(cli, "ADAPTADORES", {"contratacoes": ruim, "atas": bom})
    with pytest.raises(FalhasIngestao) as exc:
        await cli._rodar(
            ["contratacoes", "atas"], date(2026, 10, 1), date(2026, 10, 2), False, diario=True
        )
    assert exc.value.falhas == 2
    assert ruim.call_args.kwargs["atualizacoes"] is True
    bom.assert_awaited_once()
    conn.close.assert_awaited_once()


async def test_envelope_invalido_registrado_como_erro(monkeypatch):
    from pncp_ti.ingest import executar

    conn = AsyncMock()
    cliente = AsyncMock()
    cliente.list_resource.return_value = {"data": None, "totalPaginas": 1}
    registrar = AsyncMock()
    monkeypatch.setattr(executar, "registrar", registrar)
    with pytest.raises(ValueError):
        await executar.ingerir_janela(
            conn,
            cliente,
            AsyncMock(),
            entidade="teste",
            tabela="contratacoes",
            chave="numero_controle_pncp",
            path="/teste",
            janela=Janela(date(2026, 10, 1), date(2026, 10, 2)),
            filtros={},
            mapear=lambda x: x,
        )
    assert registrar.call_args.kwargs["status"] == "erro"
    assert registrar.call_args.kwargs["erro_mensagem"] == "ValueError"
    conn.commit.assert_awaited_once()


async def test_itens_bons_persistem_e_log_nao_expoe_cpf(monkeypatch, capsys):
    from pncp_ti.ingest import executar

    conn = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    conn.transaction = transaction
    cliente = AsyncMock()
    cliente.list_resource.return_value = {
        "data": [{"cpf": "12345678901"}, {"ok": True}],
        "totalPaginas": 1,
    }
    upsert = AsyncMock()
    registrar = AsyncMock()
    monkeypatch.setattr(executar, "upsert", upsert)
    monkeypatch.setattr(executar, "registrar", registrar)

    def mapear(item):
        if "cpf" in item:
            raise ValueError(f"CPF inválido: {item['cpf']}")
        return item

    with pytest.raises(FalhasIngestao):
        await executar.ingerir_janela(
            conn,
            cliente,
            AsyncMock(),
            entidade="teste",
            tabela="contratacoes",
            chave="numero_controle_pncp",
            path="/teste",
            janela=Janela(date(2026, 10, 1), date(2026, 10, 2)),
            filtros={},
            mapear=mapear,
        )
    assert upsert.await_count == 1
    assert registrar.call_args.kwargs["registros_gravados"] == 1
    output = capsys.readouterr()
    assert "12345678901" not in output.out + output.err
