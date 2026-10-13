# Referências

Rode `scripts/baixar_referencias.ps1` para salvar cópias locais das marcadas com (script).

## Fontes de dados (ADR 0016)

- SIGA RJ, CSVs regenerados diariamente:
  - https://www.compras.rj.gov.br/siga/imagens/ATA_REGISTRO_PRECO.CSV
  - https://www.compras.rj.gov.br/siga/imagens/ITENS_ATAS_REGISTRO_PRECO.CSV
  - https://www.compras.rj.gov.br/siga/imagens/PARTICIPANTES_ATAS_REGISTRO_PRECO.CSV
  - Origem dos links: Plano de Dados Abertos do RJ (SEI-120001/001511/2025):
    https://www.rj.gov.br/planejamento/sites/default/files/arquivos_paginas/SEI_102030139_Plano_de_Dados_Abertos___PDA_0.pdf
- Dados Abertos Compras.gov.br, módulo ARP: https://dadosabertos.compras.gov.br/swagger-ui/index.html
  (`/modulo-arp/1_consultarARP`, `1.2_consultarARP_FimVigencia`, `2_consultarARPItem`)
- Busca do portal PNCP (não documentada; é a usada pelo frontend):
  `https://pncp.gov.br/api/search/?q=<termo>&tipos_documento=ata&status=vigente&tam_pagina=500&pagina=1`
- Avaliado e descartado: Portal da Transparência (CGU), https://portaldatransparencia.gov.br/download-de-dados
  (não tem atas; "Licitações" até 04/2024).

## API do PNCP

- Swagger da API de Consulta: https://pncp.gov.br/api/consulta/swagger-ui/index.html
- OpenAPI da API de Consulta (script): https://pncp.gov.br/api/consulta/v3/api-docs
- OpenAPI da API PNCP (script): https://pncp.gov.br/api/pncp/v3/api-docs
- Perguntas e respostas / integração: https://www.gov.br/pncp/pt-br/integre-se-ao-pncp/perguntas-e-respostas
- Manual das APIs de consulta: baixar manualmente na página do PNCP em gov.br (o link do PDF muda a cada versão).

## Componentes reaproveitados

- MCP Compras.gov.br (`compras-mcp`): https://github.com/opedrosoares/MCP_Compras — PyPI: https://pypi.org/project/compras-mcp/ (README e manifest: script)
- `pncp-cli`: https://pypi.org/project/pncp-cli/
- `pypncp`: https://pypi.org/project/pypncp/

## Segurança

- MCP — Security Best Practices (2025-11-25) (script): https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices
- OWASP MCP Top 10 (beta): https://owasp.org/www-project-mcp-top-10/

## Normas

- Lei 14.133/2021 (script): https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm
- LGPD, Lei 13.709/2018 (script): https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- TCU — divulgação de contratos no PNCP: https://licitacoesecontratos.tcu.gov.br/5-11-7-divulgacao
