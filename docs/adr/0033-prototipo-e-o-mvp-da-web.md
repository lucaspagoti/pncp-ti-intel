# 0033 — O protótipo `prototipos/web/` é o MVP da web

- Status: aceita pelo Lucas (02/11/2026).
- Complementa a ADR 0018 e o `docs/ROADMAP-WEB.md` (W2).
- Telas e identidade visual alteradas pela ADR 0039 (W4–W6); a regra "mudar o MVP começa pelo
  protótipo" continua.

## Contexto

O `docs/ROADMAP-WEB.md` tratava o protótipo só como referência visual, e a W2 o implementava
"a partir do protótipo", sem fixar o escopo. Com o backend corrigido, o Lucas revisou as duas
telas e decidiu que elas são o MVP do frontend.

## Decisão

- `prototipos/web/` define o escopo e a referência visual do MVP: `index.html` (busca) e
  `ata.html` (detalhe). A W2 implementa essas telas em Jinja2 + HTMX, com dados reais.
- Escopo do MVP é o que aparece nas telas:
  - busca: filtros na lateral (fonte, esfera, UF, órgão, vigência mínima, faixa de preço
    unitário) com contagem por opção, campo de busca, pílulas dos filtros ativos, ordenação,
    tabela de atas com os selos `warn` e `crit` de vencimento, paginação e "Exportar CSV";
  - detalhe: dados da ata, tabela de itens com fornecedor, quantidade, limite para adesão e
    preço unitário, "Exportar itens" e "Conferir no portal";
  - layout de celular (filtros recolhíveis, tabelas empilhadas) e impressão.
- Os desvios do design system são os listados em `prototipos/web/README.md`.

## Consequências

- Funcionalidade fora do protótipo é pós-MVP e precisa de decisão do Lucas.
- Mudar o MVP começa pelo protótipo: edita-se `prototipos/web/` e depois os templates.
- O aceite da R4 continua o do `docs/ROADMAP-WEB.md` (as três buscas com dados reais).
