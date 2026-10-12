# 0002 — Consulta ao vivo via compras-mcp local

- Status: aceita (12/10/2026)

## Contexto

O MCP Compras.gov.br (`compras-mcp`, licença MIT, 100 tools) já cobre consulta ao PNCP, atas para adesão,
pesquisa de preços com descarte IQR, due diligence de fornecedor e links de Edital/TR/ETP.
Repositório: https://github.com/opedrosoares/MCP_Compras

## Decisão

Usar o `compras-mcp` como está, rodando localmente via stdio, com versão fixada (0.4.0 em 12/10/2026).

## Consequências

- Valor imediato na Fase 0, sem código próprio.
- Dependência de um projeto com um único mantenedor: versão fixada, snapshot de tools no CI e possibilidade de fork (MIT).
- Atualizar só após ler o changelog e o diff.
