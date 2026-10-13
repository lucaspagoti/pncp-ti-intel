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
- Itens da compra-mãe via endpoint PNCP `/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens`;
  resultados por item via `/itens/{numeroItem}/resultados`. O preço praticado é
  `valorUnitarioHomologado`; `valorUnitarioEstimado` é orçamento/estimativa e não pode ser rotulado
  como preço homologado. Ver [manual oficial de itens](https://pncp.gov.br/manual/pt-br/latest/contratacao/consultar_itens_de_uma_contratacao.html)
  e [resultados](https://pncp.gov.br/manual/pt-br/latest/contratacao/consultar_resultados_de_item_de_uma_contratacao.html).
- Deduplicar compras-pai referenciadas por várias atas e confirmar no piloto quais itens/resultados
  pertencem à ata específica; não atribuir automaticamente todos os itens da compra a cada ata. O
  manual lista `ordemClassificacaoSrp` nos resultados por item, mas não documenta ali um identificador
  da ATA. Só vincular preço à ATA se o piloto confirmar uma chave confiável; caso contrário, expor o
  resultado no nível da compra e marcar a associação à ATA como indisponível.
- Regra de catálogo CATMAT/CATSER nos itens (`classificar/regra.py`) só depois de confirmar que os
  campos do endpoint PNCP são suficientes para essa classificação; itens sem evidência ficam
  `INDEFINIDO`, não são descartados silenciosamente.
- Normalização de unidades (licença/mês, usuário/ano, página impressa etc.).
- Fila persistente, reprocessável e limitada por taxa; o endpoint por compra/item não é um backfill
  nacional, e a execução deve cobrir apenas as compras ligadas às atas candidatas vigentes de TI.
- Relatório de precisão/recall em `evals/`. Classificador local só se D6 não for atingido.

**Critério de aceite**
- Atas de TI vigentes consultáveis localmente, com link de fonte no PNCP; carga diária
  reexecutável sem duplicar.
- Relatório de avaliação em `evals/` a partir da amostra rotulada.
- **Portão G2:** metas da decisão D6 atingidas.

**F2A: ✅ implementada e mergeada** no PR #3 (`df301c3`, 13/10/2026), conforme ADR 0015. O trabalho
anterior `feat/f2a-itens-filtro-ti` (itens via Dados Abertos) foi descartado. O snapshot reaproveita
o motor de `ingest/executar.py`, as palavras-chave de `classificar/regra.py` e a proteção contra
sobrescrita em `classificar/amostra.py`, com amostra de atas vigentes descartadas.

**F2 ainda não aceita / F2B não iniciada.** A migração 0004 foi aplicada ao banco local depois de
backup restaurado com sucesso em banco temporário. O primeiro snapshot nacional (12/10/2026) está em
execução, limitado temporariamente a 0,5 req/s após 429 com as taxas maiores; a versão parcial ainda
não foi publicada. Rotulagem e avaliação D6/G2 continuam pendentes, assim como itens e preços. Antes
de iniciar F3, concluir F2: terminar e avaliar a F2A, implementar F2B e registrar o portão G2.

## F3 · MCP pncp-ti v1

**Status: preparada no roadmap; início condicionado ao aceite da F2.**

**Insumo necessário:** Lucas revisar e completar `insumos/perguntas_reais.csv` com 20 perguntas que
realmente faria. O arquivo atual contém seis sugestões antigas, algumas fora do escopo atual (preços,
contratos e anexos); elas não contam como perguntas validadas.

**Escopo e limites:** registrar `pncp-ti` ao lado de `compras-mcp`, ambos via stdio. Consultas locais
devem usar SQL parametrizado/fixo e o papel `mcp_reader`, somente sobre `v_atas_ti_vigentes`; nunca
aceitar SQL do modelo nem ler tabelas-base. Preços dependem da F2B. “Novas atas” deve significar atas
vigentes por data de publicação, não histórico de mudanças entre snapshots. Cada tool deve cobrir uma
lacuna que o `compras-mcp` não atende.

**Entregas**
- Servidor `pncp-ti` (FastMCP, stdio), registrado em `.mcp.json` ao lado do servidor `compras`.
- Tools de busca por objeto/órgão/UF e atas vigentes por período de publicação; tool de preço por item
  só após a F2B disponibilizar esses dados.
- Log de auditoria por chamada sem dados pessoais; schema/snapshot das tools coberto no CI.
- Testes de autorização que provem acesso apenas à view e recusa de escrita/SQL arbitrário.

**Critério de aceite**
- As 20 perguntas revisadas respondidas corretamente, com link de fonte do PNCP e indicação clara
  quando a base local não contém dados para responder.
- **Portão G3:** 2 semanas de uso real; lista do que faltou alimenta as fases seguintes.

**Prompt de abertura (usar quando F2 estiver aceita):**

```text
Leia CLAUDE.md, docs/PLANO.md, docs/FASES.md e as ADRs 0003, 0007, 0008, 0009, 0011, 0012 e 0015.
Vamos iniciar a Fase 3, já com a F2 aceita. Revise as 20 perguntas em insumos/perguntas_reais.csv
e confronte cada uma com as capacidades atuais do compras-mcp e com os dados realmente disponíveis.
Antes de codar, proponha o plano em modo plan e aguarde minha aprovação. Preserve stdio, SQL fixo e
parametrizado, papel mcp_reader e acesso exclusivamente à view v_atas_ti_vigentes. Não implemente
preços sem dados F2B nem alegue histórico entre snapshots. Inclua auditoria sem dados pessoais,
testes de permissões e snapshot de tools no CI.
```

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
