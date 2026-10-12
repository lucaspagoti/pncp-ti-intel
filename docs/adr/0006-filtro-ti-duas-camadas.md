# 0006 — Filtro de TI em duas camadas

- Status: aceita (12/10/2026)

## Contexto

O SIGA-RJ usa catálogo próprio de materiais e serviços. Itens do RJ podem chegar ao PNCP sem código
CATMAT/CATSER ou com código genérico.

## Decisão

1. Regra determinística por código de catálogo e palavras-chave.
2. Classificador pequeno, rodando localmente, para os casos que a regra não decide.

## Consequências

- Avaliação contra amostra rotulada manualmente (`insumos/amostra_rotulada.csv`, gerada na Fase 3).
- Metas de precisão e recall definidas pelo Lucas após a primeira amostra (decisão D6).
