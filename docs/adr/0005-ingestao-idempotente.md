# 0005 — Ingestão idempotente por upsert

- Status: aceita (12/10/2026)

## Decisão

Toda gravação é upsert com chave natural = número de controle PNCP. A carga é feita por janelas de datas,
com log de execução (janela, registros lidos, gravados, falhas, duração).

## Consequências

- Qualquer janela pode ser reprocessada sem duplicar.
- Uma falha no meio retoma da última janela concluída.
- Critério de aceite da Fase 2: processar a mesma janela duas vezes e obter as mesmas contagens.
