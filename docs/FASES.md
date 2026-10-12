# Fases do projeto

Cada fase começa só quando a anterior cumpre o critério de aceite. Os portões (G1, G2, G3) são decisões do Lucas: seguir, ajustar ou parar.

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

## F1 · Reconciliação

**Insumo necessário:** `insumos/contratos_ti_pge.csv` preenchido.

**Entregas**
- Spike comparando `pypncp`, `pncp-cli` e o cliente interno do `compras-mcp`; escolha registrada em ADR.
- Script que puxa 12 meses de contratos da PGE-RJ no PNCP e cruza com `insumos/contratos_ti_pge.csv`.
- Perfil dos itens do RJ: percentual com código CATMAT/CATSER, percentual com código genérico ou ausente.

**Critério de aceite**
- Relatório em `docs/relatorios/F1-cobertura.md` com: % dos contratos da lista encontrados no PNCP; % de itens com código de catálogo útil.
- **Portão G1:** Lucas decide se a cobertura basta para seguir só com o PNCP.

## F2 · Base histórica

**Entregas**
- Schema e migrações (contratações, itens, contratos, atas, órgãos, fornecedores, log de execução).
- Ingestão diária e backfill em janelas de datas, idempotente (ADR 0005).
- Papéis `ingest` (escrita) e `mcp_reader` (só `SELECT` em views).
- Backup diário com `pg_dump`.

**Critério de aceite**
- A mesma janela processada duas vezes gera as mesmas contagens.
- Backfill do período combinado concluído.
- Restauração do backup testada em banco limpo.

## F3 · Filtro de TI e preços

**Insumo necessário:** Lucas rotula a amostra gerada em `insumos/amostra_rotulada.csv`.

**Entregas**
- Regra por código de catálogo e palavras-chave + classificador local (ADR 0006).
- Geração da amostra para rotulagem e relatório de precisão/recall.
- Normalização de unidades (licença/mês, usuário/ano, página impressa etc.).

**Critério de aceite**
- Relatório de avaliação em `evals/`.
- **Portão G2:** metas da decisão D6 atingidas.

## F4 · MCP pncp-ti v1

**Insumo necessário:** `insumos/perguntas_reais.csv` com 20 perguntas.

**Entregas**
- Servidor `pncp-ti` (FastMCP, stdio), registrado em `.mcp.json`.
- Tools só de SQL: histórico de preços de TI por item, série de contratações de TI, novidades do período.
- Logs de auditoria por chamada; tools no snapshot.

**Critério de aceite**
- As 20 perguntas respondidas com link de fonte no PNCP.
- **Portão G3:** 2 semanas de uso real; lista do que faltou alimenta as fases seguintes.

## F5 · Anexos e RAG

**Entregas**
- Download dos anexos pelos links do PNCP; extração recursiva de ZIP; texto de PDF.
- Container de extração sem rede, com limite de tamanho e proteção contra ZIP bomb.
- Chunking, embeddings locais, busca híbrida; tool `buscar_trechos_anexos` com trechos delimitados e fonte.

**Critério de aceite**
- Recall@5 medido em perguntas com resposta conhecida.
- Teste com anexo contendo instrução maliciosa: a instrução não é seguida e o trecho sai marcado.

## F6 · Operação

**Entregas**
- Digest diário de novas contratações de TI no bot Hermes.
- Healthcheck diário da API (incluindo `compras_healthcheck`) e alerta de falha.
- Painel opcional, no design system da PGE.

**Critério de aceite**
- Uma semana de digests sem intervenção manual.

## F7 · Homelab

**Entregas**
- Migração do Compose para o homelab.
- HTTP com token atrás de proxy, só se o Hermes exigir.
- Revisão contra o OWASP MCP Top 10.

**Critério de aceite**
- Checklist de segurança preenchido; restauração no homelab testada.

## F8 · v1.0

**Entregas**
- Manual de uso, runbook de operação e tutorial em vídeo.

**Critério de aceite**
- Outra pessoa da GTI usa o sistema só com o manual.
