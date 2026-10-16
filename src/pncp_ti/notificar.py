"""Saída para a bridge WhatsApp existente, sem executar Hermes ou texto de terceiros."""

import os

import httpx

from pncp_ti.config import exigir
from pncp_ti.privacy import sanitizar


class ErroPublicacao(RuntimeError):
    pass


async def publicar(corpo: str, client: httpx.AsyncClient) -> None:
    url = exigir(os.environ.get("PNCP_TI_NOTIFY_URL"), "PNCP_TI_NOTIFY_URL")
    # A bridge limita a mensagem final a 1.200 caracteres, incluindo seu prefixo.
    if len(corpo) > 1000:
        raise ErroPublicacao("mensagem_excessiva")
    try:
        resposta = await client.post(
            url,
            content=sanitizar(corpo).encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        resposta.raise_for_status()
        if resposta.json().get("ok") is not True:
            raise ErroPublicacao("bridge_recusou")
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        # Não vazar URL, tokens, corpo HTTP ou texto de origem no journald.
        raise ErroPublicacao(type(exc).__name__) from None
