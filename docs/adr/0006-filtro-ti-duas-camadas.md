# 0006 — Filtro de TI em duas camadas

- Status: aceita (12/10/2026); generalizada em 13/10/2026 (ADR 0011 — escopo nacional, sem vínculo institucional)

## Contexto

Nem todo item publicado no PNCP traz um código CATMAT/CATSER útil: estados e municípios podem usar
catálogo próprio de materiais e serviços (ex: SIGA no Estado do RJ) que não mapeia bem para o catálogo
federal, e alguns itens chegam ao PNCP sem código ou com código genérico — isso vale pra qualquer órgão
do país, não só um estado específico.

## Decisão

1. Regra determinística por código de catálogo e palavras-chave.
2. Classificador pequeno, rodando localmente, para os casos que a regra não decide.

## Consequências

- Avaliação contra amostra rotulada manualmente (`insumos/amostra_rotulada.csv`, gerada na Fase 3).
- Metas de precisão e recall definidas pelo Lucas após a primeira amostra (decisão D6).
