"""Notificação isolada, frescor e contrato do gancho PNCP; sem rede real."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from pncp_ti import operacao
from pncp_ti.notificar import ErroPublicacao, publicar
from pncp_ti.operacao import SP, alertas

AGORA = datetime(2026, 10, 16, 8, 30, tzinfo=SP)


def carga(
    fonte, *, idade=0, status="concluida", ativa=True, contagens=None, coletor="api_consulta"
):
    instante = AGORA - timedelta(hours=idade)
    return dict(
        fonte=fonte,
        iniciado_em=instante,
        concluido_em=instante,
        status=status,
        ativa=ativa,
        data_referencia=instante.date(),
        geracao={"atas": {"last_modified": instante.isoformat()}},
        contagens=(contagens or {})
        | ({"coletor": coletor} if fonte == "pncp_busca" and coletor else {}),
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
    # A falha da carga já foi avisada de madrugada pelo OnFailure; 08:30 não repete.
    assert codigos(cargas) == {"siga_rj:velha"}


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
        # Termo que não respondeu hoje reaproveita a carga (ADR 0028): não é incidente.
        (None, None),
        (False, None),
        (-1, None),
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
    assert "pncp:velha" in codigos([carga("pncp_busca", idade=49)], "notebook")
    # Falha da carga é avisada pelo OnFailure da carga; 08:30 não repete.
    assert "pncp:zero" not in codigos(
        [carga("pncp_busca", status="falhou", ativa=False)], "notebook"
    )


def test_resumo_numa_frase_simples():
    cargas = [carga("siga_rj", idade=49), carga("pncp_busca", idade=49)]
    assert operacao.resumo(alertas(cargas, AGORA, "notebook")) == (
        "Atas de TI: SIGA RJ sem atualizar há mais de 2 dias; Compras.gov.br sem dados; "
        "busca PNCP sem atualizar há mais de 2 dias."
    )
    assert operacao.resumo([]) is None


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

    conexoes = []

    async def sem_banco(*args, **kwargs):
        conexoes.append(kwargs.get("connect_timeout"))
        raise operacao.psycopg.OperationalError("banco fora")

    monkeypatch.setattr(operacao, "publicar", fake)
    monkeypatch.setattr(operacao.psycopg.AsyncConnection, "connect", sem_banco)
    assert await operacao.executar("falha", "pncp-ti-backup.service") == 0
    assert await operacao.executar("falha", "pncp-ti-carga.service") == 0
    assert await operacao.executar("falha", "pncp-ti-web.service") == 0
    # Só a carga consulta o banco para dizer a fonte, com timeout curto e frase genérica se falhar.
    assert conexoes == [5]
    assert mensagens == [
        "Atas de TI: o backup de hoje falhou.",
        "Atas de TI: a atualização de hoje falhou; o site segue com os dados anteriores.",
        "Atas de TI: o site parou de funcionar.",
    ]
    with pytest.raises(ValueError):
        await operacao.executar("falha", "$(touch bad)")


def test_meia_noite_brasilia_difere_do_dia_utc():
    assert datetime(2026, 10, 17, 1, tzinfo=UTC).astimezone(SP).date() == AGORA.date()


def _falha(fonte, erro_tipo):
    return {"fonte": fonte, "status": "falhou", "erro_tipo": erro_tipo}


def test_falha_da_carga_diz_a_fonte_e_o_motivo():
    assert operacao.frase_carga([_falha("siga_rj", "codificacao")]) == (
        "o SIGA RJ não atualizou hoje (arquivo fora do padrão); "
        "o site segue com os dados anteriores"
    )


def test_falha_de_duas_fontes_numa_frase_na_ordem_da_carga():
    falhas = [_falha("pncp_busca", "termos_falhos"), _falha("siga_rj", "codificacao")]
    assert operacao.frase_carga(falhas) == (
        "o SIGA RJ (arquivo fora do padrão) e a busca PNCP (portal sem responder alguns termos "
        "há 14 dias) não atualizaram hoje; o site segue com os dados anteriores"
    )


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [
        ("ComprasTimeoutError", " (fonte fora do ar)"),
        ("ReadTimeout", " (fonte fora do ar)"),
        ("UniqueViolation", ""),
        (None, ""),
    ],
)
def test_motivo_de_excecao_sem_tipo_conhecido(tipo, esperado):
    assert operacao.frase_carga([_falha("compras_arp", tipo)]) == (
        f"o Compras.gov.br não atualizou hoje{esperado}; o site segue com os dados anteriores"
    )


def test_sem_falha_registrada_usa_a_frase_generica():
    assert operacao.frase_carga([]) == operacao.FALHAS["pncp-ti-carga.service"]


async def test_leitura_bloqueada_no_banco_cai_na_frase_generica(monkeypatch):
    async def bloqueada(inicio):
        await asyncio.sleep(3600)  # conectou, mas a leitura de `cargas` não volta

    monkeypatch.setattr(operacao, "PRAZO_BANCO", 0.05)
    monkeypatch.setattr(operacao, "_ler_falhas", bloqueada)
    assert await operacao.falhas_de_hoje(AGORA) == []


def test_termo_defasado_da_busca_pncp_avisa_numa_frase():
    """ADR 0037: a carga publica com termo pendente há 3+ dias; a operação avisa."""
    base = [carga("siga_rj"), carga("compras_arp")]
    contagens = {
        "termos_defasados": {"materiais de informatica": "2026-10-09", "toner": "2026-10-13"}
    }
    avisos = dict(alertas([*base, carga("pncp_busca", contagens=contagens)], AGORA))
    assert avisos["pncp:defasada"] == (
        "a busca PNCP está com 2 termos sem atualizar há 7 dias (portal instável)"
    )
    um = {"termos_defasados": {"toner": "2026-10-13"}}
    avisos = dict(alertas([*base, carga("pncp_busca", contagens=um)], AGORA))
    assert avisos["pncp:defasada"].startswith("a busca PNCP está com 1 termo sem atualizar há 3")


@pytest.mark.parametrize("defasados", [None, {}, {"x": "não é data"}, ["lista"]])
def test_sem_termo_defasado_valido_nao_avisa(defasados):
    contagens = {} if defasados is None else {"termos_defasados": defasados}
    cargas = [carga("siga_rj"), carga("compras_arp"), carga("pncp_busca", contagens=contagens)]
    assert "pncp:defasada" not in codigos(cargas)


def test_defasado_so_conta_na_carga_ativa():
    contagens = {"termos_defasados": {"toner": "2026-10-01"}}
    cargas = [
        carga("siga_rj"),
        carga("compras_arp"),
        carga("pncp_busca", ativa=False, status="substituida", contagens=contagens),
    ]
    assert "pncp:defasada" not in codigos(cargas)


def test_carga_pncp_da_reserva_avisa():
    """ADR 0038: a carga ativa da fonte veio da busca do portal, não da API oficial."""
    base = [carga("siga_rj"), carga("compras_arp")]
    oficial = carga("pncp_busca", contagens={"coletor": "api_consulta"})
    reserva = carga("pncp_busca", coletor=None)
    assert "pncp:reserva" not in codigos([*base, oficial])
    assert "pncp:reserva" in codigos([*base, reserva])
    assert "pncp:reserva" not in codigos(base)  # sem carga ativa, nada a dizer aqui


def test_delta_pncp_com_janela_truncada_avisa():
    """ADR 0038: marca d'água com mais de 30 dias; o delta leu só o último mês."""
    base = [carga("siga_rj"), carga("compras_arp")]
    truncada = carga("pncp_busca", contagens={"janela_truncada": True})
    assert "pncp:lacuna" in codigos([*base, truncada])
    assert "pncp:lacuna" not in codigos([*base, carga("pncp_busca")])


def test_falha_da_semente_mensal_tem_frase_propria():
    assert "varredura mensal" in operacao.FALHAS["pncp-ti-semente.service"]
