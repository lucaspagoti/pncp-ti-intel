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

Ainda na **Fase 0 (Fundação)** — nem começada a implementação. Falta:
- Instalar/registrar `compras-mcp` localmente via stdio (`.mcp.json` já tem a entrada, versão `0.4.0` fixada
  — falta efetivamente testar que sobe).
- `pyproject.toml` com `uv`, `Makefile`, `docker-compose.yml` (Postgres, porta só em `127.0.0.1`).
- CI (lint, testes, varredura de segredos) + pre-commit.
- Teste de snapshot das tools do `compras-mcp`.
- Critério de aceite da Fase 0: Claude responde a uma pergunta real usando o `compras-mcp` local;
  `make test` verde; `make up` sobe o Postgres.

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
