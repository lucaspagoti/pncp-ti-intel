# Fases do projeto

Cada fase começa só quando a anterior cumpre o critério de aceite. Os portões (G2, G3 — numeração
histórica, mantida mesmo sem G1 depois da remoção da antiga Fase de Reconciliação) são decisões do Lucas:
seguir, ajustar ou parar.

Prompt-padrão de abertura (substitua N e cole o bloco da fase):

```
Leia CLAUDE.md, docs/PLANO.md e docs/adr/. Vamos executar a Fase N.
<bloco da fase abaixo>
Antes de codar: verifique o que o compras-mcp e as bibliotecas existentes já resolvem,
proponha o plano da fase em modo plan e espere minha aprovação.
```

---

## F0 · Fundação

**Entregas**
- `compras-mcp` instalado localmente e registrado em `.mcp.json` (stdio, versão fixada).
- Repositório: `pyproject.toml` com `uv`, `Makefile`, `docker-compose.yml` com Postgres (porta só em `127.0.0.1`).
- CI com lint, testes e varredura de segredos; pre-commit.
- Teste de snapshot da lista de tools do `compras-mcp` (falha se nome ou descrição mudar).

**Critério de aceite**
- Claude responde "quais atas vigentes de outsourcing de impressão existem?" usando o `compras-mcp` local.
- `make test` verde; `make up` sobe o Postgres.

**Status: ✅ concluída** (13/10/2026, tag `f0-fundacao`).

## F1 · Base histórica

**Entregas**
- Schema e migrações (contratações, itens, contratos, atas, órgãos, fornecedores, log de execução).
- Ingestão diária e backfill em janelas de datas, idempotente (ADR 0005).
- Papéis `ingest` (escrita) e `mcp_reader` (só `SELECT` em views).
- Backup diário com `pg_dump`.

**Critério de aceite**
- A mesma janela processada duas vezes gera as mesmas contagens.
- Backfill do período combinado concluído.
- Restauração do backup testada em banco limpo.

## F2 · Filtro de TI e preços

**Insumo necessário:** Lucas rotula a amostra gerada em `insumos/amostra_rotulada.csv`.

**Entregas**
- Regra por código de catálogo e palavras-chave + classificador local (ADR 0006).
- Geração da amostra para rotulagem e relatório de precisão/recall.
- Normalização de unidades (licença/mês, usuário/ano, página impressa etc.).

**Critério de aceite**
- Relatório de avaliação em `evals/`.
- **Portão G2:** metas da decisão D6 atingidas.

## F3 · MCP pncp-ti v1

**Insumo necessário:** `insumos/perguntas_reais.csv` com 20 perguntas.

**Entregas**
- Servidor `pncp-ti` (FastMCP, stdio), registrado em `.mcp.json`.
- Tools só de SQL: histórico de preços de TI por item, série de contratações de TI, novidades do período.
- Logs de auditoria por chamada; tools no snapshot.

**Critério de aceite**
- As 20 perguntas respondidas com link de fonte no PNCP.
- **Portão G3:** 2 semanas de uso real; lista do que faltou alimenta as fases seguintes.

## F4 · Anexos e RAG

**Entregas**
- Download dos anexos pelos links do PNCP; extração recursiva de ZIP; texto de PDF.
- Container de extração sem rede, com limite de tamanho e proteção contra ZIP bomb.
- Chunking, embeddings locais, busca híbrida; tool `buscar_trechos_anexos` com trechos delimitados e fonte.

**Critério de aceite**
- Recall@5 medido em perguntas com resposta conhecida.
- Teste com anexo contendo instrução maliciosa: a instrução não é seguida e o trecho sai marcado.

## F5 · Operação

**Entregas**
- Digest diário de novas contratações de TI no bot Hermes.
- Healthcheck diário da API (incluindo `compras_healthcheck`) e alerta de falha.
- Painel opcional.

**Critério de aceite**
- Uma semana de digests sem intervenção manual.

## F6 · Exposição pública autenticada

**Entregas**
- Domínio próprio + reverse proxy com TLS (ex: Caddy/Let's Encrypt).
- Autenticação na frente de tudo — mecanismo definido na decisão D7 (ex: Tailscale Funnel com auth,
  Cloudflare Access, Authelia, Basic Auth + TLS). Nenhum serviço interno (Postgres, MCPs) exposto direto.
- HTTP dos MCPs (se necessário) só atrás desse proxy, nunca em `0.0.0.0` sem autenticação (ADR 0009).
- Revisão contra o OWASP MCP Top 10.

**Critério de aceite**
- Checklist de segurança preenchido; acesso remoto testado funcionando só com a autenticação correta (e
  recusando sem ela).

## F7 · v1.0

**Entregas**
- Manual de uso e runbook de operação (pra você mesmo lembrar como opera, meses depois).

**Critério de aceite**
- Você consegue operar o sistema do zero (restaurar backup, subir tudo, confirmar que está respondendo)
  só com o manual, sem depender da memória desta conversa.
