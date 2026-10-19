# Roadmap da web (W0–W2)

Fecha a R4 (`docs/FASES.md`), cujo aceite é a demonstração do Lucas. Fica fora das fases R. Cada
fase é uma sprint. Decisões em 19/10/2026: o Codex é o QA executor (ADR 0029), o Playwright
entra no grupo dev e no CI, e o deploy segue o rito abaixo.

A stack não muda (ADR 0018): FastAPI + Jinja2 + HTMX, sem framework JavaScript nem build com
Node. O protótipo visual está em `prototipos/web/`; o design system de referência fica fora do Git.

## W0 · Esteira de QA (sprint 1)

Sem mudar a web.

- ADR 0029 e governança (`AGENTS.md`, `CLAUDE.md`, skill `ade-workflow`).
- Skill `.agents/skills/qa-web/SKILL.md`, que o Codex aplica.
- `review-qa` (clone de QA, Postgres descartável, caixa `bwrap`, parecer com `deploy_aprovado`).
- Playwright no grupo dev, `make e2e` e job `e2e` no CI.
- E2E de base da web atual em `tests/e2e/`.
- **Aceite:** o Codex roda a esteira no snapshot da W0 e aprova.

Conhecido para a W2: o botão "Buscar" da web atual não tem nome acessível (o `<label>` em volta
só tem `&nbsp;`); o E2E o localiza por CSS até lá.

## W1 · Backend da web (sprint 2)

- Migração 0010 com `v_cargas_web` (fonte, data de referência e conclusão da carga ativa) e
  GRANT para `web_reader`, testada e reversível.
- Em `consultas.py`: facetas (contagem por opção de filtro), `filtros_ativos` e
  `dias_restantes` com nível (`warn` ≤ 90 dias, `crit` ≤ 30, hoje em `America/Sao_Paulo`).
- Rota `/ata/{fonte}/{id}/itens.csv` com `gerar_csv` e fórmulas neutralizadas.
- `scripts/smoke_web.sh`: `/saude`, as três buscas do aceite, CSP, detalhe e CSV.
- A interface ainda não muda.
- **Aceite:** testes e E2E verdes, QA aprovado e migração aplicada no deploy com backup validado.

## W2 · Frontend da web (sprint 3)

- O gerador de tokens ganha o destino `src/pncp_ti/web/static/tokens.css`.
- Templates `base.html`, `index.html`, `_resultados.html` (alvo HTMX) e `ata.html` a partir do
  protótipo; filtros com `hx-get` e `hx-push-url`; no celular, recolhimento por checkbox; tema
  único claro.
- A CSP continua a mesma; `test_web` passa a recusar `style=` e hex fora dos tokens.
- E2E: desktop 1366 e celular 390, HTMX, impressão, contraste e captura de referência visual.
- **Aceite da R4:** o Lucas pesquisa "outsourcing de impressão", "notebook" e
  "licença Microsoft" com os dados reais.

## Rito de cada sprint

1. Plano da sprint em modo plan, aprovado pelo Lucas.
2. Branch própria e TDD; Claude roda `make test` e `make e2e`.
3. Commit do snapshot e `review-qa`; o Codex aplica a skill `qa-web`. No máximo duas rodadas de
   correção; depois disso, a sprint fica `BLOCKED`.
4. PR com CI verde em `test`, `e2e`, `secrets-scan` e `vuln-scan`.
5. Claude pede o merge mostrando o parecer (`deploy_aprovado: true`). Sem isso, não pede.
6. Com o "sim" do Lucas, nesta ordem:
   1. merge (`gh pr merge --merge --delete-branch --match-head-commit`);
   2. `make backup` e `make migrate`, quando houver migração;
   3. `systemctl --user restart pncp-ti-web`;
   4. `scripts/smoke_web.sh` (a partir da W1).

   Se o smoke falhar, Claude abre um PR de revert com rollback da migração e avisa o Lucas.
