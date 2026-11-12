# 0044 — Busca centralizada em tela larga

- Status: aceita pelo Lucas (12/11/2026), depois de comparar cinco opções num HTML interativo
  (atual, centralizar o conjunto, centralizar só a lista, lista de 1200 px e painel de preços à direita).
- Complementa a ADR 0039.

## Contexto

Na página de resultados, a lateral de filtros (`--lateral`, 248 px) e a lista (`--coluna`, 1000 px)
ficavam presas à esquerda. Em monitor de 1920 px sobravam cerca de 620 px vazios à direita, e a página
pendia para um lado, enquanto a home e o detalhe já eram centralizados. A leitura não sofria: a coluna
de 1000 px mantém os títulos legíveis e o preço perto do título.

## Decisão

1. **Lateral e lista centralizadas juntas.** A `.casca` ganha `max-width: var(--casca)` e
   `margin-inline: auto`. O vazio vira duas margens iguais; filtros continuam colados à lista.
2. **Token novo `--casca`**, derivado dos existentes: `--lateral + --coluna + --s-4 + --s-6`
   (os respiros da `.principal`), 1296 px. Nenhum valor avulso.
3. **Nada mais muda.** `--coluna` segue em 1000 px; telas de até 1296 px ficam idênticas, e os
   breakpoints de 900 e 600 px também.

## Alternativas recusadas

- **Centralizar só a lista:** o vazio passaria para entre filtros e resultados (cerca de 300 px).
- **Lista de 1200 px:** linhas longas, preço mais longe do título e detalhe também mais largo.
- **Painel de preços à direita:** útil para pesquisa de preço, mas é funcionalidade nova, com o risco
  de uma mediana misturar especificações e unidades. Fica como ideia para uma fase própria.

## Consequências

- Em monitores muito largos ainda há margem, agora dos dois lados, como na home e no detalhe.
- Em 1366 px (notebook comum) entram margens de cerca de 35 px de cada lado.
- O E2E confere a centralização em 1920 px e que 1280 px continua sem margem externa.
