# Leia-me — para o Codex (ou qualquer agente que continuar o trabalho)

Este arquivo é o handoff entre sessões/agentes diferentes trabalhando no mesmo projeto.
**Atualize-o sempre que parar de trabalhar**, antes de encerrar a sessão: o que foi feito, o que falta,
e qualquer decisão nova. Não deixe o próximo agente (ou o Lucas) ter que reconstruir o contexto lendo o chat.

## Antes de fazer qualquer coisa

1. Leia nesta ordem: `CLAUDE.md` → `docs/PLANO.md` → `docs/FASES.md` → `docs/adr/` (todas) → este arquivo.
2. Respeite o "Ciclo de cada fase" do `CLAUDE.md`: proponha o plano da fase em modo plan e **espere a aprovação do Lucas**
   antes de implementar. Não pule essa etapa mesmo que pareça óbvio.
3. As regras fixas do `CLAUDE.md` (seção "Regras fixas") não são negociáveis — releia antes de tocar em
   rede, SQL, segredos ou anexos.

## Ambiente real (não é o que o pacote original presumia)

- **Não há Windows/WSL2.** Tudo roda neste servidor Linux (`homelab`), acessado via SSH. A ADR 0008
  ("local primeiro, portável para o homelab") já está satisfeita desde o início — estamos operando
  direto no que seria o destino da Fase 7. O `CLAUDE.md` ainda cita "Windows com Docker Desktop/WSL2"
  na seção Stack; isso está desatualizado e deveria ser corrigido para refletir Linux nativo + Docker.
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

- `perguntas_reais.csv` — 20 perguntas-sugestão já carregadas, status "sugestão - revisar". Lucas ainda
  precisa revisar/confirmar antes da Fase 4.
- `contratos_ti_pge.csv` — **vazio** (só cabeçalho). Bloqueia a Fase 1. Precisa ser preenchido pelo Lucas.
- `amostra_rotulada.csv` — vazio, **correto por enquanto** (é gerado pelo sistema na Fase 3; não preencher antes).
- `insumos/normas/` — vazio. Falta o regulamento estadual de pesquisa de preços do RJ (decisão D5) e
  normas internas de TI que o Lucas queira referenciar.

## Onde estamos no roadmap (`docs/FASES.md`)

**Fase 0 (Fundação) concluída** (branch `feat/f0-fundacao`, a mergear). O que foi entregue:
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
  job `secrets-scan` roda gitleaks-action). **Não testado em CI real ainda** — só localmente. Primeira
  execução de um PR no GitHub vai validar se o workflow passa de fato.
- `make test` e `make up`/`make down` verificados localmente nesta sessão — todos passaram.

**Pendências que ficaram de fora do escopo da F0 (de propósito, ver plano aprovado):**
- `src/pncp_ti/` (ingest/classify/normalize/attachments/mcp_server) — começa na Fase 1/2.
- Alembic/schema do Postgres — Fase 2.
- `pre-commit install` não foi rodado (hooks configurados mas não instalados no `.git/hooks` local).
- `scripts/baixar_referencias.ps1` é PowerShell — não roda neste servidor Linux. Se for útil, portar para
  Python/bash numa fase futura (não bloqueia nada agora).

**Critério de aceite da Fase 0 — status:**
- ✅ `make test` verde (lint + format-check + 2 testes, incluindo chamada real ao PNCP via `compras-mcp`).
- ✅ `make up` sobe o Postgres saudável, só em `127.0.0.1:5432`.
- ✅ Resposta a uma pergunta real via `compras-mcp` local, comprovada pelo teste de fumaça automatizado.
  A demonstração interativa no chat do Claude Code fica pendente para quando o Lucas abrir uma sessão
  com `cwd` na raiz do projeto (o `.mcp.json` só carrega no início da sessão).

**Próximo passo:** abrir PR de `feat/f0-fundacao` para `master`, revisão (CLAUDE.md pede revisão por
subagente de segurança + critério de aceite antes do merge), depois seguir para a **Fase 1
(Reconciliação)** — que precisa de `insumos/contratos_ti_pge.csv` preenchido pelo Lucas antes de começar.

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
