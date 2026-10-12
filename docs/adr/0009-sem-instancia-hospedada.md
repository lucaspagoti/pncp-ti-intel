# 0009 — Nunca usar a instância hospedada pública do compras-mcp

- Status: aceita (12/10/2026)

## Contexto

A extensão `.mcpb` padrão do `compras-mcp` não roda o servidor localmente: ela conversa com um servidor
hospedado por terceiro. O modo HTTP do servidor sobe em `0.0.0.0` sem autenticação.

## Decisão

Usar apenas a instalação local via stdio (Opção 2 do README do projeto). Se HTTP for necessário no futuro,
só atrás de proxy com token e escutando em `127.0.0.1`.

## Consequências

- As consultas da PGE não passam por servidor de terceiro (não revelam o que a PGE está estudando).
