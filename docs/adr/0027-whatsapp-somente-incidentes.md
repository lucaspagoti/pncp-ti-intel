# 0027 — WhatsApp somente para incidentes

- Status: aceita pelo Lucas (18/10/2026).
- Altera a ADR 0022 (decisões 2 a 4); mantém a outbox, os alertas e o `OnFailure`.

## Contexto

O digest diário "Novas atas de TI" mandou várias mensagens no WhatsApp. O Lucas decidiu
que esse canal serve só para incidentes, do servidor ou desta aplicação.

## Decisão

- `pncp_ti.operacao` não prepara mais digest de atas novas. Continuam os alertas de
  frescor e falha por fonte, o gancho PNCP e a mensagem `OnFailure` das units.
- A entrega ignora qualquer chave `digest:` ainda pendente na outbox. Nada é apagado:
  `notificacoes`, `digest_atas` e `atas_vistas` são preservadas, sem migração.
- As novidades continuam consultáveis pela web (`primeira_vez_vista`).

## Consequências

Voltar a ter digest exige nova decisão do Lucas e outro canal ou opt-in explícito.
