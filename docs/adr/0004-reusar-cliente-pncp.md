# 0004 — Ingestão reusa clientes HTTP existentes

- Status: aceita (12/10/2026); atualizada pela ADR 0016 em 13/10/2026.
- Fase 1: `compras_mcp.clients.pncp.PNCPClient`; R2: reuso de `DadosAbertosClient` para ARP.

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

- Reusar o cliente existente para endpoints cobertos pelo `compras-mcp`, com a versão travada.
- Para download SIGA e busca PNCP, não cobertos por esse cliente, a ADR 0016 permite
  clientes finos com timeout, retry e limite de tamanho.
- O motor ainda depende de `PNCPClient`; sua generalização e o adaptador ARP pertencem à R2.

## Implementação na Fase 1 (histórico)

A camada fina `ingest/client.py`, removida na R0, envolvia o PNCPClient já instalado e travado com compras-mcp.
Paginação, transporte HTTP e erros continuam nessa biblioteca; validação de envelopes, limites de
taxa e retries de ingestão ficam no projeto. As novas fontes ainda não foram implementadas na R0.
