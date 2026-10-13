# 0005 — Ingestão idempotente por upsert

- Status: aceita (12/10/2026); aplicada pela ADR 0015 a um snapshot diário das atas vigentes
  (janela = o dia), com publicação atômica do resultado.

## Decisão

As atas usam a chave lógica `snapshot_id + numeroControlePNCPAta`. A carga diária percorre a janela
do dia inteiro, com log por página e publicação atômica do snapshot somente após concluir sem falhas.

## Consequências

- Qualquer janela pode ser reprocessada sem duplicar.
- Uma falha preserva o snapshot anterior; a próxima execução recomeça a paginação, pois os offsets
  da fonte são mutáveis (ADR 0013).
- Critério de aceite da Fase 2: processar a mesma janela duas vezes e obter as mesmas contagens.
