# 0046 — A ata flutua ao passar o mouse

- Status: aceita pelo Lucas (12/11/2026), que pediu a mesma sensação dos cartões de categoria da home.
- Complementa as ADRs 0039 e 0043.

## Contexto

O cartão de categoria da home (ADR 0043) sobe 1 px e a sombra cresce em 180 ms quando o mouse passa.
O cartão de ata da lista só trocava a sombra, de uma vez e sem transição: parecia "acender", e não
"levantar".

## Decisão

1. **A ata ganha o mesmo movimento da categoria:** transição de `--dur-1` na sombra e no
   `transform`, e `translateY(-1px)` com `--shadow-lift` no hover e no foco de teclado. Só 1 px:
   numa lista longa, mais que isso fica agitado.
2. **Com `prefers-reduced-motion: reduce`, nada se move**: a ata e a categoria só trocam a sombra.
   Corrige também a categoria, que subia mesmo nesse caso.

## Consequências

- Sem token novo. O E2E confere o movimento no hover e a ausência dele com movimento reduzido.
