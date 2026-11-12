"""Coleta dos links do PRODERJ (ADR 0042): parse com fixture, prioridade e contrato do site."""

from pathlib import Path

import httpx
import pytest
from proderj_dados import CASOS_PROCESSO

from pncp_ti.fontes import proderj
from pncp_ti.fontes.siga_csv import ErroValidacao

FIXTURES = Path(__file__).parent / "fixtures" / "proderj"
VAZIA = "<html><body><div class='view-content'></div></body></html>"


def pagina(nome: str) -> str:
    return (FIXTURES / f"{nome}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(("texto", "esperado"), CASOS_PROCESSO)
def test_normalizar_processo(texto, esperado):
    assert proderj.normalizar_processo(texto) == esperado


def test_extrair_lista_pega_so_os_titulos_e_ve_a_proxima_pagina():
    entradas, ha_proxima = proderj.extrair_lista(pagina("homologadas_p0"), "homologadas")
    assert [e.node_id for e in entradas] == [1779, 1777]  # menu (217) e rodapé (999) não entram
    assert "MICROSOFT" in entradas[0].titulo and "&" not in entradas[0].titulo
    assert ha_proxima is True
    _, ha_proxima = proderj.extrair_lista(pagina("homologadas_p1"), "homologadas")
    assert ha_proxima is False


def test_o_mesmo_processo_em_duas_listas_fica_com_a_homologada():
    entradas = [
        *proderj.extrair_lista(pagina("fracassadas_p0"), "fracassadas")[0],
        *proderj.extrair_lista(pagina("homologadas_p0"), "homologadas")[0],
    ]
    links = proderj.consolidar(entradas)
    microsoft = links["430002/30/2024"]
    assert (microsoft.node_id, microsoft.lista) == (1779, "homologadas")
    assert microsoft.url == "https://www.rj.gov.br/proderj/node/1779"
    assert "430002/55/2024" in links


def test_mesma_lista_fica_com_o_node_mais_novo():
    e = [
        proderj.Entrada(10, "SEI-430002/000001/2025 A", "realizadas"),
        proderj.Entrada(20, "SEI-430002/000001/2025 B", "realizadas"),
    ]
    assert proderj.consolidar(e)["430002/1/2025"].node_id == 20


async def test_ler_site_segue_a_paginacao_de_cada_lista():
    paginas = {
        ("homologadas", "0"): pagina("homologadas_p0"),
        ("homologadas", "1"): pagina("homologadas_p1"),
        ("andamento", "0"): pagina("andamento_p0"),
        ("realizadas", "0"): pagina("realizadas_p0"),
        ("fracassadas", "0"): pagina("fracassadas_p0"),
    }
    pedidos = []

    async def baixar(client, url, params):
        lista = url.rsplit("/", 1)[1]
        pedidos.append((lista, params["page"], params["items_per_page"]))
        return paginas.get((lista, params["page"]), VAZIA)

    entradas = await proderj.ler_site(None, baixar)
    assert ("homologadas", "1", "50") in pedidos and ("homologadas", "2", "50") not in pedidos
    assert {e.lista for e in entradas} == {"homologadas", "andamento", "realizadas", "fracassadas"}
    links = proderj.validar(entradas)
    assert links["430002/719/2024"].lista == "andamento"
    assert len(links) == 4  # 30/2024, 55/2024, 719/2024 e a chamada pública 1597/2024


async def test_lista_que_nunca_acaba_e_erro_de_contrato():
    async def baixar(client, url, params):
        return pagina("homologadas_p0")  # sempre com "próxima"

    with pytest.raises(ErroValidacao) as erro:
        await proderj.ler_site(None, baixar)
    assert erro.value.tipo == "contrato"


def test_site_com_outra_marcacao_vira_erro_de_contrato():
    mudou = '<div class="titulo"><a href="/proderj/node/1">SEI-430002/000001/2025</a></div>'
    entradas, _ = proderj.extrair_lista(mudou, "homologadas")
    assert entradas == []
    with pytest.raises(ErroValidacao) as erro:
        proderj.validar(entradas)
    assert erro.value.tipo == "contrato"


def test_sem_nenhum_processo_sei_reconhecido_e_erro_de_contrato():
    so_outro_orgao = [proderj.Entrada(1, "SEI - 120211/001283/2020 - X", "homologadas")]
    with pytest.raises(ErroValidacao) as erro:
        proderj.validar(so_outro_orgao)
    assert erro.value.tipo == "contrato"


def _cliente(resposta) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(resposta))


async def test_http_inesperado_nao_tenta_de_novo():
    chamadas = []

    def resposta(request):
        chamadas.append(1)
        return httpx.Response(404)

    async with _cliente(resposta) as client:
        with pytest.raises(ErroValidacao) as erro:
            await proderj._baixar(client, "https://www.rj.gov.br/proderj/x", {})
    assert erro.value.tipo == "http" and len(chamadas) == 1


async def test_erro_do_servidor_tenta_tres_vezes_e_vira_rede(monkeypatch):
    async def sem_espera(_):
        return None

    monkeypatch.setattr(proderj.asyncio, "sleep", sem_espera)
    chamadas = []

    def resposta(request):
        chamadas.append(1)
        return httpx.Response(503)

    async with _cliente(resposta) as client:
        with pytest.raises(ErroValidacao) as erro:
            await proderj._baixar(client, "https://www.rj.gov.br/proderj/x", {})
    assert erro.value.tipo == "rede" and len(chamadas) == proderj.TENTATIVAS


async def test_pagina_acima_do_limite_e_recusada(monkeypatch):
    monkeypatch.setattr(proderj, "LIMITE_BYTES", 100)

    def resposta(request):
        return httpx.Response(200, content=b"x" * 500)

    async with _cliente(resposta) as client:
        with pytest.raises(ErroValidacao) as erro:
            await proderj._baixar(client, "https://www.rj.gov.br/proderj/x", {})
    assert erro.value.tipo == "tamanho"
