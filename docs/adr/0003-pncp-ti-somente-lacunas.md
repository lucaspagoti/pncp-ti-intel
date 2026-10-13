# 0003 — O servidor pncp-ti expõe só o que o compras-mcp não faz

- Status: aceita (12/10/2026); alterada pela ADR 0015 (12/10/2026): sai "histórico local".
  A base guarda só atas vigentes de TI.
- **Alterada pela ADR 0018 (13/10/2026):** a interface principal passa a ser a web própria; o MCP vai para o backlog.

## Contexto

Duplicar tools gera confusão para o modelo (duas tools parecidas) e manutenção dobrada.

## Decisão

O `pncp-ti` é um segundo servidor MCP, ao lado do `compras-mcp` no mesmo cliente. Ele cobre apenas:
snapshot local de atas vigentes candidatas a TI, preços normalizados, busca em anexos e digest. Sem fork do `compras-mcp`.

## Consequências

- Escopo pequeno e testável.
- Cada tool nova precisa justificar por que o `compras-mcp` não atende.
