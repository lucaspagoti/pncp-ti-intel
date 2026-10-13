# 0018 — Interface web própria; MCP sai do caminho crítico

- Status: aceita (13/10/2026), decisão do Lucas.
- Altera: ADR 0003 (o servidor `pncp-ti` via MCP deixa de ser a interface principal) e ADR 0012 (a
  exposição no domínio deixa de ser a última fase).

## Contexto

O objetivo de uso passou a ser "pesquisar um objeto e ver as atas de TI vigentes". Isso vai ser
usado no navegador, a partir do domínio pessoal do Lucas. A alternativa de usar um BI pronto
(Metabase) foi descartada: o Lucas quer algo próprio.

## Decisão

- **A interface principal é uma web própria em FastAPI + Jinja2 + HTMX.** Ela é só Python, na mesma
  stack, e não precisa de build de Node.
- **Leitura só via views,** com um papel novo `web_reader` (o mesmo modelo do `mcp_reader`: SELECT
  só em views). As consultas são fixas e parametrizadas, e nenhum SQL vem do usuário.
- **Busca:** full-text do Postgres (`portuguese` + `unaccent`) com `pg_trgm`. O pgvector (D3) fica
  adiado até existir RAG de anexos.
- O texto das fontes é dado de terceiros, então os templates usam autoescape.
- Durante o desenvolvimento, a web sobe em `127.0.0.1`. **A exposição no domínio só acontece atrás
  do reverse proxy com TLS e autenticação** (ADR 0012, decisão D7), e essa fase vem logo depois da
  web local, não no fim.
- **O MCP sai do caminho crítico.** O `.mcp.json` e os testes de snapshot e de consulta ao vivo do
  `compras-mcp` foram removidos. Um servidor MCP sobre as mesmas views pode voltar no backlog, e aí
  as regras de stdio e SQL fixo voltam a valer.

## Consequências

- A ADR 0009 continua valendo, mas perde objeto enquanto nenhum MCP estiver rodando.
- A ADR 0010 continua valendo: o `fastmcp` segue como dependência transitiva do `compras-mcp`, agora
  usado só como biblioteca e sem servidor ativo, o que reforça que o caminho vulnerável não é
  alcançável.
- A superfície exposta passa a ser HTTP. Por isso a revisão OWASP Top 10 (web) entra no critério de
  aceite da exposição.
