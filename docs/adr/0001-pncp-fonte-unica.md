# 0001 — PNCP é a fonte única; nenhum sistema próprio de órgão é integrado

- Status: aceita (12/10/2026); generalizada em 13/10/2026 (ADR 0011 — projeto sem vínculo institucional)

## Contexto

Contratos e aditivos regidos pela Lei 14.133/2021 só têm eficácia após divulgação no PNCP (art. 94).
Editais também são publicados no PNCP (art. 54). Órgãos podem ter sistema próprio de licitação (ex:
SIGA no Estado do RJ), mas o que importa juridicamente é publicado no PNCP.

## Decisão

Ingerir apenas do PNCP. Não integrar sistema próprio de nenhum órgão.

## Consequências

- Uma API, um formato, uma chave de idempotência.
- Ficam de fora: contratos antigos sob a Lei 8.666, estatais (Lei 13.303) e dados operacionais de sistemas
  próprios de órgãos (propostas, lances).
