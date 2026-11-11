# Roadmap da web (W0–W6)

Fecha a R4 (`docs/FASES.md`), cujo aceite é a demonstração do Lucas. Fica fora das fases R. Cada
fase é uma sprint. Decisões em 19/10/2026: o Codex é o QA executor (ADR 0029), o Playwright
entra no grupo dev e no CI, e o deploy segue o rito abaixo.

A stack não muda (ADR 0018): FastAPI + Jinja2 + HTMX, sem framework JavaScript nem build com
Node. O protótipo em `prototipos/web/` é a referência da web (ADR 0033), com identidade visual
própria desde a W4 (ADR 0039).

## W0 · Esteira de QA (sprint 1)

Sem mudar a web.

- ADR 0029 e governança (`AGENTS.md`, `CLAUDE.md`, skill `ade-workflow`).
- Skill `.agents/skills/qa-web/SKILL.md`, que o Codex aplica.
- `review-qa` (clone de QA, Postgres descartável, caixa `bwrap`, parecer com `deploy_aprovado`).
- Playwright no grupo dev, `make e2e` e job `e2e` no CI.
- E2E de base da web atual em `tests/e2e/`.
- **Aceite:** o Codex roda a esteira no snapshot da W0 e aprova.

Conhecido para a W2: o botão "Buscar" da web atual não tem nome acessível (o `<label>` em volta
só tem `&nbsp;`); o E2E o localiza por CSS até lá. Resolvido na W2: o E2E o acha pelo papel e
pelo nome.

## W1 · Backend da web (sprint 2)

- Migração 0010, testada e reversível:
  - `v_cargas_web` (fonte, data de referência e conclusão da carga ativa), com GRANT para
    `web_reader`;
  - busca materializada `mv_busca_atas`, atualizada depois de cada carga (ADR 0035);
  - cache `unidades_gerenciadoras`, que dá esfera, UF e município ao ARP (ADR 0034).
- Pool da web descarta conexão morta; `/saude` consulta o banco e responde 503 sem ele.
- Filtro de data passa a "vigente até pelo menos" (`vigente_ate`, `fim >= data`), como no
  protótipo.
- Em `consultas.py`: facetas (contagem por opção de filtro), `filtros_ativos` e
  `dias_restantes` com nível (`warn` ≤ 90 dias, `crit` ≤ 30, hoje em `America/Sao_Paulo`).
- Rota `/ata/{fonte}/{id}/itens.csv` com `gerar_csv` e fórmulas neutralizadas.
- `scripts/smoke_web.sh`: `/saude`, as três buscas do aceite, CSP, detalhe e CSV.
- A interface ainda não muda.
- **Aceite:**
  - testes e E2E verdes;
  - QA aprovado;
  - migração aplicada no deploy com backup validado;
  - na cópia de produção, as três buscas do aceite com as facetas abaixo de 500 ms;
  - depois da primeira carga do ARP, ao menos 95% das atas do ARP com esfera e UF.

## W2 · Frontend da web (sprint 3)

Entrega o MVP: as duas telas do protótipo com dados reais, nada além delas (ADR 0033).

- O gerador de tokens ganha o destino `src/pncp_ti/web/static/tokens.css`.
- Templates `base.html`, `index.html`, `_resultados.html` (alvo HTMX) e `ata.html` a partir do
  protótipo; filtros com `hx-get` e `hx-push-url`; no celular, recolhimento por checkbox; tema
  único claro.
- A CSP continua a mesma; `test_web` passa a recusar `style=` e hex fora dos tokens.
- E2E: desktop 1366 e celular 390, HTMX, impressão, contraste e captura de referência visual.
- **Aceite da R4:** o Lucas pesquisa "outsourcing de impressão", "notebook" e
  "licença Microsoft" com os dados reais.

Como ficou a entrega:

- o HTMX troca a casca inteira (lateral e folha), para facetas, pílulas e contador acompanharem
  os resultados; a restauração do histórico (`HX-History-Restore-Request`) recebe a página
  inteira;
- 20 atas por página e os rótulos de fonte e de ordenação do protótipo;
- a seção "Participantes: demandado × consumido" saiu do detalhe porque não está no protótipo
  (ADR 0033); a view `v_ata_consumo_item` continua no banco;
- as capturas de referência ficam em `qa-out/e2e/referencia/` (artefato do CI), sem
  comparação de pixel.

## W3 · Busca focada no item principal (primeira release)

Decidida pelo Lucas em 02/11/2026, depois de "monitor" trazer uma ata de CFTV em primeiro (ADR 0036).

- Migração 0011: `mv_busca_itens` (a cabeça do item em vetor exato e com radical),
  `mv_busca_vocabulario` e `documento` com pesos. `atualizar_busca()` atualiza as três.
- Nota de relevância pelo foco no item, preço do item buscado, linha do item que casou com o termo
  marcado, sinônimos revisados (`insumos/sinonimos_busca.txt`) e "você quis dizer".
- Avaliação `pncp_ti.busca_avaliacao`: precisão@10 de 20 buscas, antes e depois.
- **Aceite:** "monitor" com o top 10 só de atas cujo item principal é monitor; as três buscas da
  R4 sem piora; busca abaixo de 500 ms.

## W4–W6 · Redesenho do frontend (ADR 0039)

Pedido pelo Lucas em 10/11/2026: estilo limpo e minimalista, cartões arredondados
e movimento só onde ajuda. A web deixa o design system PGE Ajuda. Sem migração, sem dependência
nova e com a mesma CSP.

### W4 · Protótipo e decisão

- ADR 0039; `prototipos/web/` refeito: home (`index.html`), resultados em cartões
  (`resultados.html`), detalhe em coluna única (`ata.html`), `tokens.css` escrito à mão como fonte
  única dos valores e `prototipo.js` com o movimento.
- Sai `scripts/gerar_tokens_css.py` e o teste dele (dependiam do `tokens.json` do PGE).
- Entregue no mesmo PR da W5 e da W6.
- **Aceite (dado em 10/11/2026):** o Lucas aprovou o visual e o movimento no protótipo.

### W5 e W6 · Home, cartões, detalhe e movimento na web

O Lucas pediu o front novo em produção em 10/11/2026, e a W6 ficou pequena depois que ocultar atas
saiu do escopo (ADR 0039, item 7); por isso as duas fases, e a W4, foram entregues num PR só.

- `static/tokens.css` igual ao do protótipo (teste); `app.css` e `app.js` novos; `tokens-projeto.css`
  sai. Tamanho de fonte só pela escala (teste).
- `/` sem nenhum parâmetro preenchido mostra a home (`home.html`, só a busca, com o total e a data
  dos dados); `/?explorar=1` lista tudo. Dentro da casca (HTMX) a lista nunca volta para a home e,
  sem filtro, a URL guarda `/?explorar=1` (`HX-Push-Url`).
- Resultados em cartões, total como título, busca fixa, paginação numerada (`janela_paginas`) e
  prazo como texto, com cor só a 90 e 30 dias. Opção de filtro marcada em azul sólido, com marcador
  de rádio; o rádio cobre a linha. Filtros aplicam sozinhos (texto e preço esperam 500 ms; resposta
  velha é descartada se o leitor continuou digitando); "Aplicar filtros" saiu.
- Detalhe em coluna única: cartão-resumo, itens (a tabela rola dentro do cartão) e "Sobre este
  registro". "Voltar à busca" volta à busca como estava (histórico), ou à lista inteira.
- Movimento: o aviso de dados públicos fecha e não volta (`localStorage`), a pílula sai, a
  especificação do item abre com transição de altura e uma barra fina de progresso corre nas trocas
  do HTMX. Nada se move com `prefers-reduced-motion`.
- `scripts/smoke_web.sh` confere também a home e a lista de todas as atas.
- Testes de unidade e E2E (desktop 1366, celular 390, impressão e contraste) atualizados.
- **Aceite:** as três buscas da R4 e "monitor" com os dados reais, abaixo de 500 ms.

## W8 · Nome e ícone (ADR 0041)

Pedido pelo Lucas em 11/11/2026: a web passa a se chamar "Portal de Atas de TI" (marca, home e título das
abas) e ganha o ícone "Pilha de atas" na aba, na lateral e na home. Sem migração; alertas do WhatsApp
ficam como estão.

## W7 · Ajuste fino (ADR 0040)

Pedido pelo Lucas em 11/11/2026, depois de comparar opções num HTML: seleção de filtro em pílula
neutra, botão de busca com ícone dentro do campo (grafite, apagado com o campo vazio), tipografia Inter
servida pela própria web (`font-src 'self'`) e correções da home (campo no eixo, sem "Experimente",
rodapé legível). Sem migração.

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
