# Levantamento GitHub — 17/10/2026 (America/Sao_Paulo)

Consultas somente leitura via `gh api`, autenticado com permissão de administração.
Nenhuma configuração remota foi alterada. É um retrato datado: não substitui conferir
o estado real da PR (`gh pr checks`) em cada entrega.

| Item | Evidência observada |
| --- | --- |
| Repositório | `lucaspagoti/pncp-ti-intel`, privado |
| Branch padrão | `master` |
| Proteção do branch | `GET /branches/master`: `protected=false`, `protection.enabled=false`, checks/contexts vazios |
| Detalhes da proteção | `GET /branches/master/protection`: HTTP 403, exige GitHub Pro ou repositório público |
| Rulesets e regras efetivas | `GET /rulesets?includes_parents=true` e `GET /rules/branches/master`: HTTP 403 com a mesma exigência |
| Auto-merge | `allow_auto_merge=false` (não será habilitado) |
| Métodos permitidos | merge commit, squash e rebase habilitados; regra local exige merge commit |
| Exclusão automática de branch | `delete_branch_on_merge=false`; a branch é apagada no `gh pr merge --delete-branch` |
| Workflow | `CI`, `.github/workflows/ci.yml`, estado `active` |
| Eventos | `push` em `master` e `pull_request` (sem filtro de branch) |
| Jobs / checks disponíveis | `test`, `secrets-scan`, `vuln-scan` |

O job `test` provisiona Postgres efêmero, executa `uv sync`, `make migrate` e
`make test` (Ruff, formatação e pytest). `secrets-scan` usa Gitleaks;
`vuln-scan` usa Trivy para dependências e imagem Postgres, HIGH/CRITICAL,
com supressões justificadas em `.trivyignore`.
O pre-commit local já tem Ruff, formatação e Gitleaks.

As três execuções mais recentes de CI em `master` consultadas estavam concluídas
com sucesso; a mais recente era
[39085580048](https://github.com/lucaspagoti/pncp-ti-intel/actions/runs/39085580048),
head `e229aa9508a0d0131f0598fcaa42f011e23ebb89`.
Isso não valida o CI de uma futura alteração.

## Decisão aceita: master sem proteção

A `master` não tem proteção de branch nem rulesets, e o plano atual do GitHub não
os oferece para este repositório privado. O Lucas aceitou essa condição para este
ambiente. Consequências a manter em mente:

- O GitHub **não** exige PR, revisão nem checks para a `master`; o workflow existir
  não torna `test`, `secrets-scan` e `vuln-scan` obrigatórios.
- O controle é procedimental: PR sempre, CI verde e parecer `APPROVED` do Codex
  verificados por Claude, e merge só com autorização explícita do Lucas no chat.
- Sem push direto na `master`, sem `--admin`, sem auto-merge e sem alterar plano,
  visibilidade, proteção ou rulesets.

## Pendências para o piloto

- Autorizar uma tarefa piloto com Claude implementando e Codex revisando pelo Orca.
- Comprovar sandbox somente leitura, no máximo um Codex, relatório com veredito,
  revisão focalizada, contadores e settlement/limpeza do worker.
- Autorizar commit/push/PR do piloto; acompanhar o CI da PR até ficar verde,
  demonstrar o aceite e pedir a autorização do Lucas para mergear.
