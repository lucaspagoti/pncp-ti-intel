"""Caddyfile da exposição (R5, ADR 0024): nada chega à web sem credencial nem fora do loopback.

Teste estático, sem Docker: lê os blocos de primeiro nível e confere as regras que não podem
regredir.
"""

from __future__ import annotations

import re
from pathlib import Path

CADDYFILE = Path(__file__).parent.parent / "deploy/caddy/Caddyfile"


def _blocos(texto: str) -> list[tuple[str, list[str]]]:
    """Blocos de primeiro nível como (cabeçalho, linhas internas sem comentários)."""
    blocos: list[tuple[str, list[str]]] = []
    nivel = 0
    for bruta in texto.splitlines():
        linha = bruta.split("#", 1)[0].strip() if not bruta.lstrip().startswith("#") else ""
        if not linha:
            continue
        if nivel == 0:
            assert linha.endswith("{"), f"linha fora de bloco: {linha!r}"
            blocos.append((linha[:-1].strip(), []))
        else:
            blocos[-1][1].append(linha)
        nivel += linha.count("{") - linha.count("}")
    assert nivel == 0, "chaves desbalanceadas"
    for _, corpo in blocos:
        corpo.pop()  # a "}" que fecha o bloco
    return blocos


BLOCOS = _blocos(CADDYFILE.read_text(encoding="utf-8"))
GLOBAL = next(corpo for cab, corpo in BLOCOS if cab == "")
SNIPPETS = {cab[1:-1]: corpo for cab, corpo in BLOCOS if cab.startswith("(")}
SITES = {cab: corpo for cab, corpo in BLOCOS if cab and not cab.startswith("(")}


def _expandido(corpo: list[str]) -> list[str]:
    linhas: list[str] = []
    for linha in corpo:
        if linha.startswith("import "):
            linhas += _expandido(SNIPPETS[linha.split()[1]])
        else:
            linhas.append(linha)
    return linhas


def test_global_sem_admin_e_sem_redirecionador_na_porta_80():
    assert "admin off" in GLOBAL
    assert "auto_https disable_redirects" in GLOBAL


def test_todo_site_escuta_so_em_loopback():
    assert len(SITES) == 3
    for site, corpo in SITES.items():
        binds = [linha for linha in corpo if linha.startswith("bind ")]
        assert binds in (["bind 127.0.0.1"], ["bind {$PNCP_BIND:127.0.0.1}"]), site


def test_todo_site_que_chega_na_web_autentica_antes():
    for site, corpo in SITES.items():
        linhas = _expandido(corpo)
        proxies = [i for i, linha in enumerate(linhas) if linha.startswith("reverse_proxy")]
        if not proxies:
            assert "respond 421" in linhas, site
            continue
        auth = [i for i, linha in enumerate(linhas) if linha.startswith("basic_auth")]
        assert auth and auth[0] < proxies[0], site
        assert "{$PNCP_AUTH_USER} {$PNCP_AUTH_HASH}" in linhas, site


def test_site_do_tunnel_e_http_em_loopback_casando_pelo_dominio():
    tunnel = "http://{$PNCP_TUNNEL_HOST:atas.myhomelablp.site}:{$PNCP_TUNNEL_PORT:8444}"
    assert tunnel in SITES
    assert "import protegido" in SITES[tunnel]
    resto = "http://:{$PNCP_TUNNEL_PORT:8444}"
    assert "reverse_proxy" not in " ".join(_expandido(SITES[resto]))


def test_token_do_access_nao_vai_para_a_web_nem_para_o_log():
    protegido = _expandido(SNIPPETS["protegido"])
    assert "header_up -Cf-Access-Jwt-Assertion" in protegido
    assert "request>headers>Cf-Access-Jwt-Assertion delete" in SNIPPETS["registro"]
    # O 502 (web fora) registra a requisição original no logger padrão, não no de acesso.
    padrao = GLOBAL[GLOBAL.index("log default {") :]
    assert "request>headers>Cf-Access-Jwt-Assertion delete" in padrao
    for corpo in SITES.values():
        assert "import registro" in corpo or "import protegido" in corpo


def test_proxy_so_aponta_para_a_web_em_loopback():
    destinos = set(re.findall(r"reverse_proxy (\S+)", CADDYFILE.read_text(encoding="utf-8")))
    assert destinos == {"127.0.0.1:8000"}
