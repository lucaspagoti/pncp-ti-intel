# Leia-me — para o Codex (ou qualquer agente que continuar o trabalho)

Este arquivo é o handoff entre sessões/agentes diferentes trabalhando no mesmo projeto.
**Atualize-o sempre que parar de trabalhar**, antes de encerrar a sessão: o que foi feito, o que falta,
e qualquer decisão nova. Não deixe o próximo agente (ou o Lucas) ter que reconstruir o contexto lendo o chat.

## Seu papel: arquiteto especialista + testador, não só executor de tarefas

Você (Codex) não entra aqui só para marcar itens de uma lista. Em toda sessão neste projeto, assuma os
dois papéis abaixo, o tempo todo, sem que o Lucas precise pedir de novo:

**Arquiteto especialista.** Antes de aceitar qualquer plano, decisão ou código — seu ou de uma sessão
anterior — pergunte-se se é a escolha certa para um sistema de contratações públicas que vai informar
decisões reais da GTI/PGE-RJ. Isso inclui revisar criticamente o que já está feito, não só o que falta.
Se uma ADR, uma escolha de schema, uma dependência ou uma decisão de segurança te parecer frágil,
equivocada ou ultrapassada, diga isso ao Lucas explicitamente — com o porquê e uma alternativa concreta —
em vez de só seguir em frente. Proponha uma ADR nova quando for o caso.

**Testador.** Toda entrega nova (sua ou herdada) precisa ser de fato exercitada, não só lida. Rode
`make test`, suba o ambiente com `make up`, chame as tools do `compras-mcp` e do `pncp-ti` com perguntas
reais (comece pelas de `insumos/perguntas_reais.csv`), e tente ativamente achar onde quebra: dado
inesperado da API do PNCP, resposta vazia, schema mudou, ingestão duplicando, filtro de TI com falso
positivo/negativo, injeção via texto de anexo (regra fixa do `CLAUDE.md`). Não valide uma fase como
"pronta" só porque o código existe e compila — valide porque você tentou quebrar e não quebrou.

**Sempre que terminar algo:**
1. Diga explicitamente se o que foi feito (por você ou por quem veio antes) está correto, bem arquitetado
   e testado — ou não, com o motivo.
2. Liste pelo menos uma melhoria concreta que valeria a pena (mesmo que não seja para agora) — débito
   técnico, risco de segurança, oportunidade de simplificação, lacuna de teste. Registre no
   `LEIA-ME-CODEX.md` (seção "Log de sessões" ou uma seção nova "Melhorias sugeridas") para não se perder.
3. Isso não substitui o "Ciclo de cada fase" do `CLAUDE.md` — a crítica e os testes alimentam o plano que
   você propõe em modo plan; eles não são desculpa para implementar sem a aprovação do Lucas.

## Antes de fazer qualquer coisa

1. Leia nesta ordem: `CLAUDE.md` → `docs/PLANO.md` → `docs/FASES.md` → `docs/adr/` (todas) → este arquivo.
2. Respeite o "Ciclo de cada fase" do `CLAUDE.md`: proponha o plano da fase em modo plan e **espere a aprovação do Lucas**
   antes de implementar. Não pule essa etapa mesmo que pareça óbvio.
3. As regras fixas do `CLAUDE.md` (seção "Regras fixas") não são negociáveis — releia antes de tocar em
   rede, SQL, segredos ou anexos.

## Ambiente real (não é o que o pacote original presumia)

- **Não há Windows/WSL2.** Tudo roda neste servidor Linux (`homelab`), acessado via SSH. A ADR 0008
  ("local primeiro, portável para o homelab") já está satisfeita desde o início — estamos operando
  direto no que seria o destino da Fase 7. O `CLAUDE.md` já foi corrigido para Linux nativo + Docker. O `docs/PLANO.md` ainda tem
  D1/D2 como pendentes e referências ao ambiente antigo; sincronizar antes da próxima fase.
- Ferramentas confirmadas instaladas nesta máquina (12/10/2026):
  - Docker 29.5.0 + Docker Compose v5.1.3 — ok.
  - `uv` 0.13.0 — instalado em `~/.local/bin` (garanta que está no `PATH`).
  - `gh` CLI 2.102.0 — instalado via apt e **autenticado** como `lucaspagoti` (HTTPS).
  - Python do sistema é 3.14, mas o projeto usa Python 3.12 via `uv` (isolado, sem conflito).

## Decisões já resolvidas nesta sessão

- **D1 (repositório):** GitHub **privado pessoal** (não institucional). Criado e com push feito:
  https://github.com/lucaspagoti/pncp-ti-intel (branch `master`).
- **D2 (ambiente local):** servidor Linux via SSH, sem WSL2 (ver seção acima).
- D3–D6 (índice vetorial, modelos locais, norma de preços do RJ, metas do filtro de TI) seguem **pendentes**,
  como registrado em `docs/PLANO.md`.

## Estado dos insumos (`insumos/`)

- `perguntas_reais.csv` — 20 linhas numeradas, mas apenas **6 perguntas preenchidas**; as linhas
  7–20 estão vazias. As 6 perguntas têm status "sugestão - revisar". Lucas ainda
  precisa revisar/confirmar antes da Fase 4.
- `contratos_ti_pge.csv` — **vazio** (só cabeçalho). Bloqueia a Fase 1. Precisa ser preenchido pelo Lucas.
- `amostra_rotulada.csv` — vazio, **correto por enquanto** (é gerado pelo sistema na Fase 3; não preencher antes).
- `insumos/normas/` — vazio. Falta o regulamento estadual de pesquisa de preços do RJ (decisão D5) e
  normas internas de TI que o Lucas queira referenciar.

## Onde estamos no roadmap (`docs/FASES.md`)

**Fase 0 (Fundação) implementada, ainda não aceita para merge** (branch `feat/f0-fundacao`).
PR existente: https://github.com/lucaspagoti/pncp-ti-intel/pull/1. Revisão independente feita em
12/10/2026; há lacunas de aceite e de fixação de dependências (ver log abaixo). O que foi entregue:
- `pyproject.toml` (uv, Python 3.12, deps dev: pytest, pytest-asyncio, fastmcp, ruff, pre-commit).
- `tests/conftest.py` com o transporte stdio do `compras-mcp` (mesmo comando do `.mcp.json`).
- `tests/test_compras_mcp_snapshot.py` + `tests/snapshots/compras_mcp_tools.json` — snapshot de 100 tools,
  detecta "rug pull". Atualizar com `uv run python tests/test_compras_mcp_snapshot.py --update` só depois
  de ler o changelog/diff de uma nova versão do `compras-mcp` (regra do CLAUDE.md).
- `tests/test_compras_mcp_live_query.py` — chamada real a `compras_arp_buscar_por_objeto` (busca de ARPs
  vigentes por palavra-chave), cobrindo o critério de aceite "responde a uma pergunta real usando o
  compras-mcp local".
- `docker-compose.yml` — Postgres 16, porta só em `127.0.0.1:5432`, healthcheck. Testado: `make up` sobe
  saudável, `make down` derruba limpo.
- `Makefile` — `up`, `down`, `test` (lint + format-check + pytest) funcionais; `ingest`/`eval` são
  placeholders que apontam para as Fases 2/3.
- `.pre-commit-config.yaml` (ruff + gitleaks) e `.github/workflows/ci.yml` (job `test` roda `make test`;
  job `secrets-scan` roda gitleaks-action). **CI real executado no PR #1**: job `test` passou; `secrets-scan` falhou com HTTP 403
  ao ler commits do PR. Corrigido no commit `44a5c66`, concedendo apenas `contents: read` e
  `pull-requests: read` ao job de varredura. Resultado da execução corrigida: ver log abaixo.
- `make test` e `make up`/`make down` verificados localmente nesta sessão — todos passaram.

**Pendências que ficaram de fora do escopo da F0 (de propósito, ver plano aprovado):**
- `src/pncp_ti/` (ingest/classify/normalize/attachments/mcp_server) — começa na Fase 1/2.
- Alembic/schema do Postgres — Fase 2.
- `pre-commit install` não foi rodado (hooks configurados mas não instalados no `.git/hooks` local).
- `scripts/baixar_referencias.ps1` é PowerShell — não roda neste servidor Linux. Se for útil, portar para
  Python/bash numa fase futura (não bloqueia nada agora).

**Critério de aceite da Fase 0 — status:**
- ✅ `make test` verde (lint + format-check + 2 testes, incluindo chamada real ao PNCP via `compras-mcp`).
- ✅ `make up` sobe o Postgres saudável, só em `127.0.0.1:5432`, imagem pinada por digest.
- ✅ Teste de fumaça endurecido (13/10/2026): agora valida contrato estrutural (campos esperados em
  cada item), que `dataVigenciaFinal` respeita a janela pedida e que `objeto` de fato contém a
  palavra-chave — não só que a tool rodou. Documenta explicitamente que distinguir outsourcing real de
  falso positivo (papel, plotagem) é trabalho do classificador da Fase 3, não deste teste.
- ⏳ Demonstração interativa pelo Lucas no chat do Claude Code (com `.mcp.json` carregado) continua
  pendente — não é algo que uma sessão de terminal consiga fazer sozinha.

**Lacunas da revisão do Codex, fechadas em 13/10/2026 (mesma branch, antes do merge):**
1. Teste de fumaça fortalecido (ver acima).
2. `docs/PLANO.md` sincronizado: D1 e D2 marcados como resolvidos.
3. `compras-mcp` agora é dependência declarada em `pyproject.toml` (`==0.4.0`), travada no `uv.lock` com
   hashes — protege a árvore transitiva inteira, não só o pacote top-level (ADR 0002). `.mcp.json` e
   `tests/conftest.py` trocaram de `uvx --from ...` para `uv run --project . compras-mcp`, usando o
   ambiente travado. Testado: `uv sync`, `make test` e `make up` continuam verdes.
4. Postgres pinado por digest em `docker-compose.yml`
   (`postgres@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d`, = `postgres:16`
   em 12/10/2026). Atualizar o comentário junto do digest quando trocar de versão.
5. Job `vuln-scan` novo em `.github/workflows/ci.yml` (Trivy): varre `uv.lock` (filesystem) e a imagem do
   Postgres, falha em CRITICAL/HIGH com correção disponível. **Ainda não validado em CI real** — só
   localmente (lint/testes/up/down); confirmar na próxima execução do workflow.

**Próximo passo:** empurrar essas correções para o PR #1, confirmar que os 3 jobs de CI (`test`,
`secrets-scan`, `vuln-scan`) ficam verdes, demonstrar o critério de aceite no chat do Claude Code com o
Lucas, e então merge/tag. Depois propor o plano e aguardar aprovação para a **Fase 1 (Reconciliação)** —
que precisa de `insumos/contratos_ti_pge.csv` preenchido pelo Lucas antes de começar.

## Convenções do projeto

- Documentação e mensagens: português (Brasil). Código, nomes de variáveis e commits: inglês.
- Commits seguem conventional commits (ex: `chore:`, `feat:`, `fix:`) — ver `git log`.
- Toda decisão nova vira ADR em `docs/adr/`, numerada sequencialmente (próxima: `0010-...`).
- Nenhum segredo no repositório; `.env` é local e já está no `.gitignore`.

## Log de sessões

- **2026-10-12 (Claude/Sonnet 5, sessão inicial):** pacote descompactado, git inicializado e commitado
  (`5d1dd15`). Identidade git configurada (lucas / lucaspagoti95@gmail.com). Li todos os documentos do
  pacote. Resolvi D1 (GitHub privado pessoal) e D2 (Linux via SSH, sem WSL2) com o Lucas. Instalei `uv`
  e `gh` CLI, autentiquei `gh` como `lucaspagoti`. Criei repo privado
  https://github.com/lucaspagoti/pncp-ti-intel e dei push do commit inicial. Corrigi a referência a
  Windows/WSL2 no `CLAUDE.md` (agora: servidor Linux via SSH). Criei este arquivo.
  **Próximo passo:** propor o plano da Fase 0 em modo plan para aprovação do Lucas, depois implementar.
- **2026-10-12 (Claude/Sonnet 5, mesma sessão, Fase 0):** plano da Fase 0 aprovado pelo Lucas. Implementei
  em `feat/f0-fundacao`: tooling (`pyproject.toml`, `Makefile`, `docker-compose.yml`, pre-commit, CI),
  testes reais contra o `compras-mcp` (snapshot de 100 tools + chamada de fumaça), tudo verificado
  localmente (`make test`, `make up`/`make down`). Atualizei `README.md` e `CLAUDE.md`. Ver seção
  "Onde estamos no roadmap" acima para o detalhe completo e as pendências deixadas de propósito fora do
  escopo. **Próximo passo:** abrir PR, revisar, mergear, e depois a Fase 1.

- **2026-10-12 (Codex, revisão da F0):** li CLAUDE.md, PLANO.md, FASES.md e todas as ADRs.
  Preservei as alterações de handoff que já estavam no arquivo. Localizei PR #1 já aberto e
  anexei ao chat; fiz revisão independente por subagente (segurança e aceite). `make test` passou
  (lint, formato e 2 testes); primeiras tentativas falharam por permissões do sandbox nos caches
  do uv/uvx, não por falha da API. `.env` estava ausente: criei arquivo local com senha aleatória
  e modo 0600, sem versionar nem exibir o segredo. `make up` subiu Postgres saudável; `docker inspect`
  confirmou bind 127.0.0.1:5432; `make down` passou, preservando volume. Não há servidor `pncp-ti`
  implementado para exercitar ainda. Corrigi HTTP 403 do job secrets-scan no commit `44a5c66`,
  revisado pelo subagente e enviado ao PR.
  **Avaliação:** estratégia de composição, stdio e bind local são adequados; fundação testada,
  mas F0 ainda não plenamente aceita. Não fiz merge/tag nem iniciei F1.
  **Melhorias concretas:** (1) distinguir fumaça de resposta funcional, testar contrato do payload
  e demonstrar outsourcing com links e ressalvas de adesão/varredura parcial; (2) fixar compras-mcp
  e transitivas por lock/hashes — `uvx --from compras-mcp==0.4.0` está fora do uv.lock e snapshot
  de metadados não protege contra mudança de código; (3) fixar Postgres por digest; (4) incluir
  varredura de vulnerabilidades prevista no plano; (5) sincronizar D1/D2 e contagem de perguntas.
  **Demonstração:** candidatos retornados: Batalhão de Guarda Presidencial, ata 90003/2025
  (fim 14/10/2026, https://pncp.gov.br/app/atas/00394452000103/2025/18457/1); Câmara Municipal
  de Macapá, ata 00004/2024 (fim 15/10/2026, https://pncp.gov.br/app/atas/04188116000157/2024/2/1);
  SEFAZ/GDF, ata 00250/2024 (fim 16/10/2026, https://pncp.gov.br/app/atas/00394684000153/2024/730/1).
  A resposta da busca não comprova autorização/saldo para adesão estadual.
  **CI após correção:** jobs `test` e `secrets-scan` verdes na execução 38302340655
  (https://github.com/lucaspagoti/pncp-ti-intel/actions/runs/38302340655).
- **2026-10-13 (Claude/Sonnet 5, fechando as lacunas da revisão do Codex):** revisei os apontamentos
  (commits `44a5c66` e `f0bfd26`) um por um, confirmei que `perguntas_reais.csv` tem mesmo só 6 linhas
  preenchidas (`awk` confere). Concordei com as 5 lacunas e fechei todas na mesma branch
  `feat/f0-fundacao`: teste de fumaça agora valida contrato estrutural e janela de vigência, não só que a
  tool rodou; `docs/PLANO.md` sincronizado (D1/D2 marcados); `compras-mcp` virou dependência travada no
  `uv.lock` com hashes, `.mcp.json`/testes trocaram `uvx --from` por `uv run --project . compras-mcp`;
  Postgres pinado por digest; job `vuln-scan` (Trivy) novo no CI. `make test` e `make up`/`down`
  verificados localmente de novo após cada mudança — todos verdes. **Próximo passo:** empurrar, conferir
  CI real (3 jobs), demonstrar o critério de aceite com o Lucas no chat, então merge/tag e Fase 1.
