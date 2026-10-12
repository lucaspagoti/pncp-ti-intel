# 0004 — Ingestão reusa um cliente existente da API do PNCP

- Status: aceita (12/10/2026); escolha do cliente pendente para a Fase 1

## Contexto

A API de consulta do PNCP tem armadilhas conhecidas:
- WAF recusa conexões sem User-Agent de navegador; a API exige `Accept: application/json`.
- Endpoints de coleção paginam com 10 itens por padrão e truncam sem aviso; o tamanho máximo varia por endpoint.
- Períodos maiores que 365 dias são rejeitados (HTTP 422).
- Na listagem de contratações por publicação, o código de modalidade é obrigatório.

## Decisão

Não escrever cliente do zero. Candidatos, comparados em spike na Fase 1:
`pypncp` (assíncrono), `pncp-cli` (CLI e biblioteca, sem dependências) e o cliente interno do `compras-mcp`.

## Consequências

- Envolver o cliente escolhido numa camada fina (`src/pncp_ti/ingest/client.py`) para poder trocá-lo.
