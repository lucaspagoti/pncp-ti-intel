"""Carga do SIGA RJ no Postgres: troca atômica, idempotência, falhas e permissões."""

from dataclasses import replace
from datetime import date

import httpx
import psycopg
import pytest
import siga_dados as d
from psycopg.errors import InsufficientPrivilege
from psycopg.rows import dict_row

from pncp_ti.config import get_settings, reader_dsn
from pncp_ti.fontes import siga
from pncp_ti.fontes.siga import arquivos_de_diretorio, carregar
from pncp_ti.fontes.siga_csv import ErroValidacao


async def _carga(conn, tmp_path, conjunto):
    pasta = tmp_path / f"c{len(list(tmp_path.iterdir()))}"
    pasta.mkdir()
    d.escrever(pasta, conjunto)
    return await carregar(conn, arquivos_de_diretorio(pasta))


async def _um(conn, sql, *params):
    cur = await conn.execute(sql, params)
    return (await cur.fetchone())["n"]


async def test_carga_completa_publica_so_atas_ti_validas_e_vigentes(conn_ingest, tmp_path):
    r = await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    assert r.status == "concluida"
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 7
    ativa = await _um(
        conn_ingest, "SELECT count(*) n FROM cargas WHERE ativa AND status='concluida'"
    )
    assert ativa == 1
    cur = await conn_ingest.execute(
        "SELECT is_ti, motivo_ti, id_origem FROM atas ORDER BY id_origem"
    )
    por_id = {row["id_origem"]: row for row in await cur.fetchall()}
    assert por_id["1"]["is_ti"] and por_id["4"]["is_ti"]
    assert not por_id["2"]["is_ti"]
    assert por_id["6"]["motivo_ti"].startswith("VII-videomonitoramento:")  # catraca com CFTV
    assert por_id["7"]["motivo_ti"].startswith("I-telecom:")  # VOIP
    await conn_ingest.commit()


async def test_views_listam_so_atas_ti_vigentes_com_preco_valido(
    conn_ingest, conn_reader, tmp_path
):
    await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    cur = await conn_reader.execute(
        "SELECT id_ata, fonte, primeira_vez_vista FROM v_atas_ti_vigentes"
    )
    atas = await cur.fetchall()
    # 1 = TI válida; 4 = TI sem início; 6 = CFTV e 7 = VOIP (citados no anexo);
    # 3 interrompida e 5 vencida ficam fora
    assert {a["id_ata"] for a in atas} == {"1", "4", "6", "7"}
    assert {a["fonte"] for a in atas} == {"siga_rj"}
    assert all(a["primeira_vez_vista"] is not None for a in atas)

    cur = await conn_reader.execute(
        "SELECT id_ata, id_item, valor_unitario, valor_valido FROM v_ata_itens_ti"
    )
    itens = await cur.fetchall()
    assert {i["id_ata"] for i in itens} == {"1", "4", "6", "7"}
    assert [i for i in itens if i["id_item"] in ("12", "14")] and all(
        i["valor_unitario"] is None for i in itens if i["id_item"] in ("12", "14")
    )
    cur = await conn_reader.execute("SELECT count(*) n FROM v_ata_consumo_item")
    assert (await cur.fetchone())["n"] == 3  # 3 linhas distintas após dedupe (ata 1: 2; ata 4: 1)


async def test_reprocessar_mesmos_arquivos_nao_duplica_e_registra_sem_mudanca(
    conn_ingest, tmp_path
):
    primeira = await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    segunda = await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    assert (primeira.status, segunda.status) == ("concluida", "sem_mudanca")
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 7
    assert await _um(conn_ingest, "SELECT count(*) n FROM ata_itens") == 9
    assert await _um(conn_ingest, "SELECT count(*) n FROM cargas WHERE status='sem_mudanca'") == 1
    ativa = await (await conn_ingest.execute("SELECT id FROM cargas WHERE ativa")).fetchone()
    assert ativa["id"] == primeira.carga_id


async def test_nova_geracao_substitui_a_anterior_e_preserva_primeira_vez_vista(
    conn_ingest, tmp_path
):
    primeira = await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    await conn_ingest.execute(
        "UPDATE atas_vistas SET primeira_vez_vista = '2026-01-02' WHERE id_origem = '1'"
    )
    await conn_ingest.commit()

    atas, itens, part = d.conjunto_basico()
    alterado = (atas.replace(b"MEDICAMENTO", b"MEDICAMENTOS"), itens, part)
    segunda = await _carga(conn_ingest, tmp_path, alterado)

    assert segunda.status == "concluida"
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 7
    assert (
        await _um(conn_ingest, "SELECT count(*) n FROM atas WHERE carga_id=%s", primeira.carga_id)
        == 0
    )
    antiga = await (
        await conn_ingest.execute(
            "SELECT ativa, status FROM cargas WHERE id=%s", (primeira.carga_id,)
        )
    ).fetchone()
    assert (antiga["ativa"], antiga["status"]) == (False, "substituida")
    vista = await (
        await conn_ingest.execute("SELECT primeira_vez_vista FROM atas_vistas WHERE id_origem='1'")
    ).fetchone()
    assert vista["primeira_vez_vista"] == date(2026, 1, 2)


async def test_falha_de_validacao_mantem_a_carga_anterior_e_registra_o_erro(conn_ingest, tmp_path):
    await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    atas, itens, part = d.conjunto_basico()
    with pytest.raises(ErroValidacao):
        await _carga(conn_ingest, tmp_path, (atas.replace(b"Status da Ata", b"X"), itens, part))
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 7
    falha = await (
        await conn_ingest.execute(
            "SELECT status, erro_tipo, ativa FROM cargas WHERE status='falhou'"
        )
    ).fetchone()
    assert (falha["status"], falha["erro_tipo"], falha["ativa"]) == ("falhou", "cabecalho", False)
    assert await _um(conn_ingest, "SELECT count(*) n FROM cargas WHERE ativa") == 1


async def test_falha_no_meio_da_gravacao_faz_rollback_total(conn_ingest, tmp_path, monkeypatch):
    primeira = await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    original = siga.preparar

    def quebrado(arquivos):
        conjunto, decisoes = original(arquivos)
        decisoes["2"] = (None, "x")  # viola NOT NULL já durante o COPY
        return conjunto, decisoes

    monkeypatch.setattr(siga, "preparar", quebrado)
    atas, itens, part = d.conjunto_basico()
    with pytest.raises(psycopg.errors.NotNullViolation):
        await _carga(
            conn_ingest, tmp_path, (atas.replace(b"MEDICAMENTO", b"MEDICAMENTOS"), itens, part)
        )

    ativa = await (await conn_ingest.execute("SELECT id FROM cargas WHERE ativa")).fetchone()
    assert ativa["id"] == primeira.carga_id
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 7
    assert await _um(conn_ingest, "SELECT count(*) n FROM cargas WHERE status='em_andamento'") == 0
    assert await _um(conn_ingest, "SELECT count(*) n FROM cargas WHERE status='falhou'") == 1


async def test_queda_brusca_de_volume_nao_substitui_a_carga_ativa(conn_ingest, tmp_path):
    await _carga(conn_ingest, tmp_path, d.conjunto_grande(100))
    with pytest.raises(ErroValidacao) as exc:
        await _carga(conn_ingest, tmp_path, d.conjunto_grande(40))
    assert exc.value.tipo == "queda_volume"
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 100


async def test_arquivo_de_geracao_anterior_nao_substitui_a_ativa(conn_ingest, tmp_path):
    await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    with pytest.raises(ErroValidacao) as exc:
        await _carga(conn_ingest, tmp_path, d.conjunto_basico(geracao="12/10/2026"))
    assert exc.value.tipo == "geracao_antiga"


async def test_leitor_nao_acessa_tabelas_nem_escreve(conn_ingest, tmp_path, nome_banco_teste):
    await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    dsn = reader_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    with psycopg.connect(dsn, row_factory=dict_row) as leitor:
        assert leitor.execute("SELECT count(*) n FROM v_atas_ti_vigentes").fetchone()["n"] == 4
        for tabela in ("atas", "ata_itens", "ata_participantes", "cargas", "atas_vistas"):
            with pytest.raises(InsufficientPrivilege):
                leitor.execute(f"SELECT 1 FROM {tabela} LIMIT 1")
            leitor.rollback()
        with pytest.raises(InsufficientPrivilege):
            leitor.execute(
                "INSERT INTO cargas (id, fonte, data_referencia, status) "
                "VALUES (gen_random_uuid(), 'x', now(), 'falhou')"
            )
        leitor.rollback()
        # A view agrega várias tabelas, então nem é atualizável; de qualquer forma não escreve.
        with pytest.raises((InsufficientPrivilege, psycopg.errors.ObjectNotInPrerequisiteState)):
            leitor.execute("DELETE FROM v_atas_ti_vigentes")


# --- download ---


def _cliente(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def sem_espera(monkeypatch):
    async def _nada(_):
        return None

    monkeypatch.setattr(siga.asyncio, "sleep", _nada)


async def test_download_grava_arquivos_com_sha256_e_last_modified(tmp_path):
    atas, itens, part = d.conjunto_basico()
    corpos = {siga.ARQUIVOS["atas"]: atas, siga.ARQUIVOS["itens"]: itens,
              siga.ARQUIVOS["participantes"]: part}  # fmt: skip

    def handler(req):
        return httpx.Response(
            200,
            content=corpos[req.url.path.rsplit("/", 1)[1]],
            headers={"last-modified": "Tue, 13 Oct 2026 04:53:06 GMT"},
        )

    async with _cliente(handler) as client:
        baixados = await siga.baixar(tmp_path / "dl", client)
    assert set(baixados) == {"atas", "itens", "participantes"}
    assert baixados["atas"].caminho.read_bytes() == atas
    assert baixados["atas"].sha256 == siga._sha256(baixados["atas"].caminho)
    assert baixados["itens"].last_modified.year == 2026


async def test_download_truncado_e_tentado_de_novo_e_depois_falha(tmp_path, sem_espera):
    chamadas = []

    def handler(req):
        chamadas.append(req.url.path)
        return httpx.Response(200, content=b"abc", headers={"content-length": "10"})

    async with _cliente(handler) as client:
        with pytest.raises(ErroValidacao) as exc:
            await siga.baixar(tmp_path / "dl", client)
    assert exc.value.tipo == "rede"
    assert len(chamadas) == siga.TENTATIVAS
    assert not list((tmp_path / "dl").glob("*.part"))


async def test_http_404_nao_e_repetido(tmp_path, sem_espera):
    chamadas = []

    def handler(req):
        chamadas.append(1)
        return httpx.Response(404)

    async with _cliente(handler) as client:
        with pytest.raises(ErroValidacao) as exc:
            await siga.baixar(tmp_path / "dl", client)
    assert (exc.value.tipo, len(chamadas)) == ("http", 1)


async def test_last_modified_distante_indica_geracoes_diferentes(tmp_path):
    horas = iter(["04:53:06", "04:53:09", "07:10:00"])

    def handler(req):
        return httpx.Response(
            200, content=b"x", headers={"last-modified": f"Tue, 13 Oct 2026 {next(horas)} GMT"}
        )

    async with _cliente(handler) as client:
        with pytest.raises(ErroValidacao) as exc:
            await siga.baixar(tmp_path / "dl", client)
    assert exc.value.tipo == "geracao"


async def test_arquivo_acima_do_limite_e_recusado(tmp_path, monkeypatch):
    monkeypatch.setattr(siga, "LIMITE_BYTES", 5)

    def handler(req):
        return httpx.Response(200, content=b"123456789")

    async with _cliente(handler) as client:
        with pytest.raises(ErroValidacao) as exc:
            await siga.baixar(tmp_path / "dl", client)
    assert exc.value.tipo == "tamanho"


async def test_forcar_republica_com_os_mesmos_arquivos_e_reclassifica(
    conn_ingest, tmp_path, monkeypatch
):
    primeira = await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    pasta = tmp_path / "c0"
    arquivos = arquivos_de_diretorio(pasta)
    sem = await carregar(conn_ingest, arquivos)
    assert sem.status == "sem_mudanca"

    from pncp_ti.classificar import in05

    monkeypatch.setattr(in05, "CATEGORIAS_FORA_DE_ESCOPO", frozenset({"I-telecom"}))
    forcada = await carregar(conn_ingest, arquivos, forcar=True)

    assert forcada.status == "concluida"
    assert forcada.carga_id not in (primeira.carga_id, sem.carga_id)
    assert await _um(conn_ingest, "SELECT count(*) n FROM atas") == 7
    voip = await (
        await conn_ingest.execute("SELECT is_ti FROM atas WHERE id_origem = '7'")
    ).fetchone()
    assert voip["is_ti"] is False


async def test_queda_de_itens_nao_substitui_a_carga_ativa(conn_ingest, tmp_path):
    """I1 da revisão: arquivo de itens regenerado pela metade não pode publicar."""
    await _carga(conn_ingest, tmp_path, d.conjunto_grande(100))
    atas, itens, part = d.conjunto_grande(100)
    linhas = itens.split(b"\r\n")
    cortado = b"\r\n".join(linhas[:61]) + b"\r\n"  # cabeçalho + 60 itens
    with pytest.raises(ErroValidacao) as exc:
        await _carga(conn_ingest, tmp_path, (atas, cortado, part))
    assert exc.value.tipo in {"queda_volume", "cobertura_itens"}
    assert await _um(conn_ingest, "SELECT count(*) n FROM ata_itens") == 100


async def test_data_extracao_no_futuro_e_recusada(conn_ingest, tmp_path):
    with pytest.raises(ErroValidacao) as exc:
        await _carga(conn_ingest, tmp_path, d.conjunto_basico(geracao="01/01/2099"))
    assert exc.value.tipo == "geracao_futura"
    assert await _um(conn_ingest, "SELECT count(*) n FROM cargas WHERE ativa") == 0


async def test_mudanca_de_regra_reclassifica_sem_forcar(conn_ingest, tmp_path, monkeypatch):
    primeira = await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    from pncp_ti.classificar import in05

    monkeypatch.setattr(in05, "CATEGORIAS_FORA_DE_ESCOPO", frozenset({"I-telecom"}))
    segunda = await carregar(conn_ingest, arquivos_de_diretorio(tmp_path / "c0"))
    assert (primeira.status, segunda.status) == ("concluida", "concluida")
    voip = await (
        await conn_ingest.execute("SELECT is_ti FROM atas WHERE id_origem='7'")
    ).fetchone()
    assert voip["is_ti"] is False


async def test_falha_de_download_fica_registrada_em_cargas(conn_ingest, tmp_path, sem_espera):
    def handler(req):
        return httpx.Response(404)

    async with _cliente(handler) as client:
        with pytest.raises(ErroValidacao):
            await siga.baixar_registrando(conn_ingest, tmp_path / "dl", client)
    falha = await (
        await conn_ingest.execute("SELECT status, erro_tipo FROM cargas WHERE status = 'falhou'")
    ).fetchone()
    assert (falha["status"], falha["erro_tipo"]) == ("falhou", "http")


async def test_erro_do_driver_grava_so_classe_e_sqlstate(conn_ingest, tmp_path, monkeypatch):
    original = siga.preparar

    def quebrado(arquivos):
        conjunto, decisoes = original(arquivos)
        decisoes["2"] = (None, "x")
        return conjunto, decisoes

    monkeypatch.setattr(siga, "preparar", quebrado)
    with pytest.raises(psycopg.errors.NotNullViolation):
        await _carga(conn_ingest, tmp_path, d.conjunto_basico())
    falha = await (
        await conn_ingest.execute(
            "SELECT erro_tipo, erro_mensagem FROM cargas WHERE status='falhou'"
        )
    ).fetchone()
    assert falha["erro_tipo"] == "NotNullViolation"
    assert falha["erro_mensagem"] == "NotNullViolation sqlstate=23502"
    assert "Failing row" not in falha["erro_mensagem"]


def test_retencao_so_apaga_pastas_de_carga_com_timestamp(tmp_path):
    for nome in (
        "20260101T000000-aaaaaaaa",
        "20260102T000000-bbbbbbbb",
        "20260103T000000-cccccccc",
        "20260104T000000-dddddddd",
    ):
        (tmp_path / nome).mkdir()
    (tmp_path / "minha_pasta_de_trabalho").mkdir()
    siga._reter_ultimas(tmp_path, manter=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "20260103T000000-cccccccc", "20260104T000000-dddddddd", "minha_pasta_de_trabalho",
    ]  # fmt: skip


async def test_arquivo_baixado_fica_com_permissao_restrita(tmp_path):
    atas, itens, part = d.conjunto_basico()

    def handler(req):
        return httpx.Response(200, content=atas)

    async with _cliente(handler) as client:
        baixados = await siga.baixar(tmp_path / "dl", client)
    assert baixados["atas"].caminho.stat().st_mode & 0o777 == 0o600


async def test_destino_do_download_e_exclusivo(tmp_path):
    """P2 do Codex: duas execuções não podem compartilhar a pasta de download."""

    def handler(req):
        return httpx.Response(200, content=b"x")

    destino = tmp_path / "mesmo"
    async with _cliente(handler) as client:
        await siga.baixar(destino, client)
        with pytest.raises(FileExistsError):
            await siga.baixar(destino, client)


async def test_trava_de_sessao_impede_segunda_execucao_simultanea(conn_ingest, nome_banco_teste):
    from pncp_ti.config import get_settings, ingest_dsn

    dsn = ingest_dsn(replace(get_settings(), postgres_db=nome_banco_teste))
    outra = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
    try:
        assert await siga.tentar_trava_sessao(conn_ingest) is True
        assert await siga.tentar_trava_sessao(outra) is False
        await conn_ingest.close()  # fecha a sessão: a trava é liberada
        assert await siga.tentar_trava_sessao(outra) is True
    finally:
        await outra.close()
