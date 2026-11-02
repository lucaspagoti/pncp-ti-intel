# W2 · Frontend do MVP — revisão QA (BLOCKED após R2)

Tarefa: W2 do `docs/ROADMAP-WEB.md`, branch `feat/w2-frontend-mvp`, PR #31. Revisor: Codex pelo `review-qa`
(ADR 0029). Relatório escrito pelo coordenador (Claude) em 02/11/2026.

## Rodadas

| Rodada | Snapshot | Commit | Veredito | Achados |
|---|---|---|---|---|
| R0 | `w2-r0-05ea700` | `05ea700` | CHANGES_REQUESTED | QA-001 (P2) |
| C1/R1 | `w2-r1-3100a4a` | `3100a4a` | APPROVED, `deploy_aprovado: true` | nenhum |
| C2/R2 | `w2-r2-7152148` | `7152148` | CHANGES_REQUESTED | R2-001 (P2) |

- **QA-001 (corrigido na C1):** termo, órgão ou objeto com 200 letras sem espaço criava rolagem horizontal
  (até 4.289 px). A correção usou `overflow-wrap: anywhere`, com um E2E de regressão.
- **Por que houve a C2:** depois da R1, o Lucas autorizou validar com os dados reais (banco de produção, papel
  `web_reader`, só leitura). No detalhe de uma ata do ARP, o nº do item `00001` aparecia partido em duas linhas,
  porque o `anywhere` em todo `td` encolhia as colunas estreitas. A C2 restringiu o `anywhere` e passou os `td`
  para `break-word`. A mudança invalidou o parecer da R1.
- **R2-001 (pendente):** na impressão A4, uma descrição de item com 250 caracteres sem espaço deixa a tabela com
  3.252 px e tira o preço unitário da folha. Com o CSS da R1, a tabela cabe (792 px). Evidências do Codex:
  `qa-out/comparar.json`, `qa-out/pdf-evidencia.log` e `qa-out/token-r2.pdf` (no clone de QA, já removido). A
  correção sugerida é voltar a `overflow-wrap: anywhere` nas células descritivas em `@media print`, manter o
  `nowrap` no nº do item e acrescentar um E2E de impressão.

## Medida nos dados reais

No banco de produção (só leitura), em `v_ata_itens_ti`, o maior trecho sem espaço numa descrição tem 50
caracteres. São 21 itens com trecho acima de 40 e nenhum acima de 60. O caso do achado (250) não existe hoje.

## Estado

- Testes do implementador no `7152148`: `make test` com 509 passed e 37 skipped; `make e2e` com 36 passed.
  Também observados pelo Codex na R2.
- CI do PR #31 no `7152148`: `test`, `e2e`, `secrets-scan` e `vuln-scan` verdes, merge state `CLEAN`.
- Sem `deploy_aprovado: true` no head atual. As duas rodadas de correção acabaram, por isso a tarefa está
  `BLOCKED`. Não há merge nem deploy, e a C3 depende de decisão do Lucas.

## Reabertura (decisão do Lucas, 02/11/2026)

O Lucas aprovou um plano novo para a primeira release: frontend fiel ao protótipo, polido com as skills
frontend-design e UI UX Pro Max, mais a busca focada no item (W3, PR separado). Essa decisão reabre a W2
com escopo novo, cuja revisão recomeça em R0 com o mesmo limite de duas correções. Entram nela:

- R2-001: a descrição do item quebra em qualquer ponto, com largura mínima na tela e livre na impressão.
  O E2E de impressão usa a área útil do A4 (718 px).
- Especificação longa do item (comum no ARP) vira resumo com "Ver especificação completa" num `<details>`.
  Na impressão sai o texto inteiro.
- Carregamento do HTMX com `aria-busy` e esmaecimento só se a resposta passar de 150 ms.
- Alvos de toque de 44 px no celular e estado vazio com o próximo passo.
