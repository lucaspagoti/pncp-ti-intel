# 0045 — Barra de busca flutuante, sem faixa em volta

- Status: aceita pelo Lucas (12/11/2026), ao apontar o problema em produção.
- Complementa as ADRs 0039 e 0044.

## Contexto

Na lista, a barra de busca fica fixa no topo (`.topo`, `position: sticky`). O contêiner tinha fundo
translúcido (`--surface-veu`) com desfoque. Ao rolar, essa faixa cinza cortava os cartões brancos em
volta do campo e aparecia como um contorno feio. O Lucas pediu que só o campo ficasse por cima,
com a lista passando visível em volta dele.

## Decisão

1. **`.topo` sem fundo nem desfoque.** Só o campo é opaco; o resto da faixa é transparente.
2. **O clique atravessa a faixa** (`pointer-events: none` no `.topo` e `auto` na `.busca`): o cartão
   que passa por baixo do respiro em volta do campo continua clicável.
3. **O campo ganha a elevação da home** (`--shadow-lift`), mantendo a borda de controle e o foco azul,
   para se destacar do cartão branco que passa por baixo.
4. **Token `--surface-veu` removido**, porque ficou sem uso.

## Consequências

- No topo da página, antes de rolar, o campo da lista fica com a mesma sombra do campo da home.
- O E2E confere, depois de rolar, que o `.topo` é transparente, sem desfoque, e não captura o clique.
