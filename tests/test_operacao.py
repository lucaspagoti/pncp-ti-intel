"""Notificação isolada, frescor e contrato do gancho PNCP; sem rede real."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from pncp_ti import operacao
from pncp_ti.notificar import ErroPublicacao, publicar
from pncp_ti.operacao import SP, alertas

AGORA = datetime(2026, 10, 16, 8, 30, tzinfo=SP)


def carga(fonte, *, idade=0, status="concluida", ativa=True, contagens=None):
    instante = AGORA - timedelta(hours=idade)
    return dict(
        fonte=fonte,
        iniciado_em=instante,
        concluido_em=instante,
        status=status,
        ativa=ativa,
        data_referencia=instante.date(),
        geracao={"atas": {"last_modified": instante.isoformat()}},
        contagens=contagens or {},
    )


def codigos(cargas, termo=None):
    return {codigo for codigo, _ in alertas(cargas, AGORA, termo)}


def test_frescor_por_fonte_falha_arp_nao_esconde_siga_parado():
    cargas = [
        carga("siga_rj", idade=49),
        carga("compras_arp", idade=24),
        carga("compras_arp", status="falhou", ativa=False),
        carga("siga_rj", status="sem_mudanca", ativa=False),
    ]
    assert codigos(cargas) == {"siga_rj:velha", "compras_arp:falhou"}


def test_limite_48h_estrito_e_carga_ausente():
    assert codigos([carga("siga_rj", idade=48), carga("compras_arp", idade=48)]) == set()
    assert codigos([]) == {"siga_rj:ausente", "compras_arp:ausente"}


def test_siga_sem_last_modified_usa_data_origem_nao_execucao_recente():
    siga = carga("siga_rj")
    siga["geracao"] = {}
    siga["data_referencia"] = (AGORA - timedelta(days=3)).date()
    assert "siga_rj:velha" in codigos([siga])


@pytest.mark.parametrize(
    "total, esperado",
    [
        (0, "pncp:zero"),
        (4, None),
        (None, "pncp:sem_metrica"),
        (False, "pncp:sem_metrica"),
        (-1, "pncp:sem_metrica"),
    ],
)
def test_gancho_pncp_parametrizavel(total, esperado):
    cargas = [
        carga("siga_rj"),
        carga("compras_arp"),
        carga("pncp_busca", contagens={"resultados_por_termo": {"notebook": total}}),
    ]
    assert codigos(cargas, "notebook") == ({esperado} if esperado else set())
    assert codigos(cargas) == set()  # R3 pode continuar ausente até configurar o termo.


def test_pncp_ausente_antigo_ou_falhando_nao_vira_zero():
    assert "pncp:indisponivel" in codigos([], "notebook")
    assert "pncp:velha" in codigos([carga("pncp_busca", idade=49)], "notebook")
    assert "pncp:indisponivel" in codigos(
        [carga("pncp_busca", status="falhou", ativa=False)], "notebook"
    )


@pytest.mark.parametrize(
    "status,payload",
    [
        (200, {"ok": True}),
        (200, {"ok": False}),
        (503, {"ok": True}),
        (200, {"ok": "true"}),
        (200, []),
        (200, "invalid JSON"),
    ],
)
async def test_publicacao_exige_confirmacao_e_nao_expoe_segredos(monkeypatch, status, payload):
    monkeypatch.setenv("PNCP_TI_NOTIFY_URL", "http://bridge.invalid/notify/text?token=SECRET")
    chamadas = []

    def handler(req):
        chamadas.append(req)
        if isinstance(payload, str):
            return httpx.Response(status, text=payload)
        return httpx.Response(status, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        if status == 200 and payload == {"ok": True}:
            await publicar("Ata 123.456.789-09", client)
        else:
            with pytest.raises(ErroPublicacao) as exc:
                await publicar("Ata 123.456.789-09", client)
            assert "SECRET" not in str(exc.value)
    assert len(chamadas) == 1
    assert "123.456.789-09" not in chamadas[0].content.decode()
    assert chamadas[0].headers["content-type"] == "text/plain; charset=utf-8"


async def test_timeout_nao_reenvia_automaticamente(monkeypatch):
    monkeypatch.setenv("PNCP_TI_NOTIFY_URL", "http://bridge.invalid/notify/text")
    chamadas = []

    def handler(req):
        chamadas.append(req)
        raise httpx.ReadTimeout("secret URL")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ErroPublicacao, match="ReadTimeout"):
            await publicar("texto", client)
        with pytest.raises(ErroPublicacao, match="excessiva"):
            await publicar("x" * 1001, client)
    assert len(chamadas) == 1


async def test_onfailure_independe_do_banco(monkeypatch):
    mensagens = []

    async def fake(corpo, client):
        mensagens.append(corpo)

    async def sem_banco(*args, **kwargs):
        raise AssertionError("OnFailure não deve conectar ao Postgres")

    monkeypatch.setattr(operacao, "publicar", fake)
    monkeypatch.setattr(operacao.psycopg.AsyncConnection, "connect", sem_banco)
    assert await operacao.executar("falha", "pncp-ti-backup.service") == 0
    assert "pncp-ti-backup.service" in mensagens[0]
    with pytest.raises(ValueError):
        await operacao.executar("falha", "$(touch bad)")


def test_meia_noite_brasilia_difere_do_dia_utc():
    assert datetime(2026, 10, 17, 1, tzinfo=UTC).astimezone(SP).date() == AGORA.date()
