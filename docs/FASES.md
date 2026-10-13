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

## F1 · Infraestrutura de ingestão

Redefinida pela ADR 0015 (12/10/2026). O backfill nacional de contratações, atas e contratos
foi cancelado: o projeto passou a guardar só atas de TI vigentes. O que a F1 entrega e
continua valendo é o motor.

**Entregas**
- Motor de ingestão por janelas, idempotente (ADR 0005): paginação, retry/backoff, savepoint
  por item, log de execução, tratamento do 204 vazio do PNCP.
- Papéis `ingest` (escrita) e `mcp_reader` (só `SELECT` em views); privacidade de fornecedor
  (ADR 0013).
- Backup com `pg_dump` e restauração em banco novo.

**Critério de aceite**
- A mesma janela processada duas vezes gera as mesmas contagens. ✅ (teste de idempotência)
- Restauração do backup testada em banco limpo. ✅ (cluster novo, ver `LEIA-ME-CODEX.md`)
- ~~Backfill do período combinado concluído.~~ Cancelado pela ADR 0015.

**Status: mergeada** (PR #2, confirmado no GitHub nesta revisão). Os adaptadores históricos
saem do código na F2A; o backfill continua cancelado.

## F2 · Atas de TI vigentes e preços

**Insumo necessário:** Lucas rotula a amostra gerada em `insumos/amostra_rotulada.csv`.

**2A — Atas de TI vigentes**
- Snapshot diário de `/v1/atas` (janela = hoje, ~484 mil vigentes, mínimo teórico de ~80 min) com filtro de TI na
  entrada: palavras-chave generosas no `objetoContratacao`. Só candidatas são gravadas.
- Cada carga guarda também uma amostra pequena das descartadas, para medir recall.
- View `v_atas_ti_vigentes` (`vigencia_fim >= hoje`, não cancelada) para o `mcp_reader`.
- Remoção dos adaptadores/tabelas de `contratacoes`, `contratos` e `itens_contratacao` (migração
  própria) e do código de itens via Dados Abertos (ADR 0014 substituída).
- `make amostra` sobre atas: candidatas + descartadas, para o Lucas rotular.

**2B — Itens e preços das atas de TI**
- Itens e valores registrados vindos da compra-mãe de cada ata no PNCP (uma consulta por compra,
  N = recorte de TI). Regra de catálogo CATMAT/CATSER nos itens (`classificar/regra.py`).
- Normalização de unidades (licença/mês, usuário/ano, página impressa etc.).
- Relatório de precisão/recall em `evals/`. Classificador local só se D6 não for atingido.

**Critério de aceite**
- Atas de TI vigentes consultáveis localmente, com link de fonte no PNCP; carga diária
  reexecutável sem duplicar.
- Relatório de avaliação em `evals/` a partir da amostra rotulada.
- **Portão G2:** metas da decisão D6 atingidas.

**Status: implementação revisada pelo Codex a pedido do Lucas, preparada para PR** (branch `feat/f2-atas-vigentes-ti`, ADR 0015). O trabalho anterior
`feat/f2a-itens-filtro-ti` (itens via Dados Abertos) não segue. Reaproveitamos o motor de
`ingest/executar.py`, as palavras-chave de `classificar/regra.py` e a proteção contra sobrescrita
em `classificar/amostra.py`; o snapshot substitui a amostragem de itens por candidatas e descartadas.
A migração 0004 e o snapshot nacional não foram executados no banco de desenvolvimento.

## F3 · MCP pncp-ti v1

**Insumo necessário:** `insumos/perguntas_reais.csv` com 20 perguntas.

**Entregas**
- Servidor `pncp-ti` (FastMCP, stdio), registrado em `.mcp.json`.
- Tools só de SQL sobre atas de TI vigentes: busca por objeto/órgão/UF, preço registrado por item,
  novas atas do período.
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
- Digest diário de novas atas de TI vigentes no bot Hermes.
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
