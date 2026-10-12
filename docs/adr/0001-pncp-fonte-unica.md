# 0001 — PNCP é a fonte única; SIGA-RJ fica fora

- Status: aceita (12/10/2026)

## Contexto

Contratos e aditivos regidos pela Lei 14.133/2021 só têm eficácia após divulgação no PNCP (art. 94).
Editais também são publicados no PNCP (art. 54). O SIGA-RJ é onde o Estado licita, mas publica no PNCP.

## Decisão

Ingerir apenas do PNCP. Não integrar o SIGA-RJ.

## Consequências

- Uma API, um formato, uma chave de idempotência.
- Ficam de fora: contratos antigos sob a Lei 8.666, estatais (Lei 13.303) e dados operacionais do SIGA (propostas, lances).
- A cobertura real do RJ no PNCP é verificada na Fase 1 (portão G1). Se for insuficiente, esta ADR é revista.
