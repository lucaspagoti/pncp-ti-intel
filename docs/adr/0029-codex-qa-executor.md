# 0029 — Codex como QA executor isolado

- Status: aceita pelo Lucas (19/10/2026).
- Altera o papel do Codex definido em `AGENTS.md`, `CLAUDE.md` e na skill `ade-workflow`
  (revisor somente leitura). O `review-exec` somente leitura continua valendo para mudanças sem
  execução.

## Contexto

O roadmap da web (`docs/ROADMAP-WEB.md`) troca a interface inteira (W2) e muda o backend da web
(W1). A revisão somente leitura do Codex não roda testes: o sandbox `read-only` bloqueia até os
arquivos temporários do pytest, e o Codex não alcança o Postgres. Para uma interface, isso deixa
de fora justamente o que mais quebra: navegação real, HTMX, CSP no navegador e layout.

O Lucas decidiu que o Codex vira o QA e executa tudo (suíte, banco de teste e E2E), num ambiente
descartável e sem acesso ao `.env` real. O deploy passa a depender do parecer dele.

Na exploração, o sandbox `workspace-write` do Codex mostrou-se insuficiente sozinho: ele restringe
escrita, não leitura. Com rede liberada, um Codex sem isolamento extra leria o `.env` real, o
token do `gh`, `/opt/homelab/secrets/` e o socket do Docker (equivalente a root), e alcançaria o
Postgres de produção em `127.0.0.1:5432`.

## Decisão

1. **Papel.** O Codex executa, no clone de QA, `make migrate`, `make test`, `make e2e` e o
   teste exploratório da skill `.agents/skills/qa-web/SKILL.md`. Ele nunca altera o repositório
   de trabalho, o GitHub, o banco de produção nem serviços. Claude continua implementando,
   corrigindo e registrando; o Codex não corrige código.
2. **Ambiente** (`.claude/skills/ade-workflow/scripts/review-qa`):
   - clone independente do commit do snapshot (`git clone --no-hardlinks`), apagado ao fim;
   - Postgres de QA em contêiner próprio (`scripts/pg_descartavel.sh`), mesmo digest pinado,
     porta aleatória só em `127.0.0.1` e senhas geradas na hora, num `.env` sintético;
   - dependências instaladas antes, fora da caixa (`uv sync` com `UV_LINK_MODE=copy`, Chromium
     do Playwright); dentro, `uv` roda offline e sem sync.
3. **Caixa `bwrap`** por lista de permissão em volta do `codex exec`:
   - só `/usr` e `/etc` (somente leitura), `/tmp` vazio, `/run` só com o DNS;
   - `$HOME` vazio, onde voltam o clone de QA (leitura e escrita), um `CODEX_HOME` temporário
     (só `auth.json` e config mínima, sem plugins, hooks nem MCP) e os binários e caches
     necessários (somente leitura);
   - `/opt`, `/srv`, `/var`, `/mnt`, `/root`, o resto do `$HOME`, o socket do Docker, do Orca e do
     SSH não existem na caixa; ambiente limpo (`env -i`);
   - namespaces próprios de usuário, PID, IPC e UTS, sem capabilities e sem criar userns
     aninhado (`--disable-userns`);
   - `review-qa isolamento` prova isso antes do uso e entra no PR que mudar a caixa.
4. **Codex:** `--sandbox danger-full-access`, `approval_policy="never"`,
   `features.multi_agent=false`, `--ephemeral`, timeout de 3.600 s. **A caixa é a fronteira.**
   O sandbox próprio do Codex (`workspace-write`) usa `bwrap`, e o AppArmor do Ubuntu
   (`apparmor_restrict_unprivileged_userns=1`) não deixa um `bwrap` criar namespace dentro de
   outro; o modo landlock legado também exige `bwrap`. Comprovado no smoke de 19/10/2026: o
   Codex não executou nenhum comando e devolveu `CHANGES_REQUESTED`. A caixa externa é mais
   restritiva que o `workspace-write` (que lê o disco inteiro): escrita só no clone, no
   `CODEX_HOME` temporário e em `/tmp` vazio, e leitura só pela lista de permissão.
5. **Parecer:** `references/parecer-qa.schema.json` acrescenta `deploy_aprovado` (booleano) e
   `evidencias` (comando, resultado, arquivo). `validar_parecer.py --qa` só aceita
   `deploy_aprovado: true` com `APPROVED` e exige evidências. O worktree de trabalho tem o
   fingerprint conferido antes e depois.
6. **Gate de deploy da web:** parecer `APPROVED` com `deploy_aprovado: true` do snapshot, CI
   verde (`test`, `e2e`, `secrets-scan`, `vuln-scan`) e o "sim" do Lucas no PR. Depois do merge,
   Claude faz backup, migração (se houver), restart do `pncp-ti-web` e o smoke pós-deploy.
7. **Não muda:** classificação P0–P3, no máximo duas rodadas de correção, um Codex por vez,
   nenhum outro agente, merge manual com `--match-head-commit`.

## Riscos aceitos

- **Codex sem sandbox próprio.** Se a caixa falhar ao montar, o `bwrap` não executa nada (não há
  modo degradado). `review-qa isolamento` deve passar antes de cada uso novo da esteira.
- **Rede aberta na caixa.** É necessária para o TCP com o Postgres de QA e para a API do Codex.
  O Codex alcança a internet e a porta do Postgres de produção, mas sem credenciais: nenhum
  segredo existe dentro da caixa. Um ataque por conteúdo de terceiros (prompt injection nos
  dados de teste ou no diff) poderia, no pior caso, enviar para fora o próprio código do
  repositório (privado) e os dados sintéticos de QA.
- **Token do Codex.** O `auth.json` entra numa cópia temporária; se o Codex renovar o token, a
  renovação mais nova volta ao `~/.codex` ao fim.
- **Escrita no clone.** O Codex pode alterar o clone de QA (é descartável); por isso o parecer só
  vale para o commit do snapshot, e a evidência fica no `OUT_DIR` do coordenador.

## Consequências

- O QA cobre comportamento real (banco, navegador, CSP) e não só leitura de diff.
- Cada rodada de QA custa mais tempo (minutos de suíte e E2E) do que a revisão somente leitura.
- O homelab depende das bibliotecas do Chromium extraídas sem sudo
  (`scripts/playwright_libs.sh`); no CI, `playwright install --with-deps`.
- Mudar a caixa, o schema ou o gate exige rever esta ADR.
