# 0011 — Escopo nacional, sem vínculo institucional

- Status: aceita (13/10/2026)
- **Alterada pela ADR 0016 (13/10/2026):** o escopo continua nacional e passa a incluir o Estado do RJ via SIGA (fonte de dados pública, não vínculo institucional).

## Contexto

O pacote inicial do projeto foi escrito com a GTI/PGE-RJ como usuário-alvo: citava a PGE em toda a
documentação, tinha uma fase inteira (Reconciliação) dedicada a cruzar contratações do PNCP com uma
lista própria de contratos de TI da PGE-RJ (`insumos/contratos_ti_pge.csv`, nunca preenchida), e um
filtro de TI em duas camadas (ADR 0006) motivado especificamente pelo catálogo próprio do Estado do RJ
(SIGA). O Lucas decidiu, antes de qualquer fase além da F0, que este é um **projeto pessoal** — não
institucional, sem vínculo com nenhum órgão específico.

## Decisão

1. Remover toda referência à PGE/GTI-RJ da documentação do projeto.
2. Remover a fase de Reconciliação por completo — não há (nem haverá) uma lista de referência de
   contratos de nenhum órgão específico pra cruzar e medir cobertura.
3. Escopo de dados passa a ser **nacional**: todo o PNCP, não só o Rio de Janeiro.
4. O critério de "o que é contratação de TI" continua sendo curadoria pessoal do Lucas (mesma lógica de
   regra + classificador da ADR 0006) — só deixa de estar atrelado ao catálogo ou às necessidades de um
   órgão específico.
5. Finalidade de uso (para efeito de LGPD, já que a base trata dado público — Lei 13.709/2018, art. 7º,
   §3º): pesquisa e aprendizado pessoal, não mais "apoiar o planejamento de contratações de TI de um
   órgão".

## Consequências

- `docs/FASES.md` perde a antiga Fase 1 (Reconciliação); as fases seguintes são renumeradas. O portão G1
  (fim da Reconciliação) deixa de existir; G2 e G3 mantêm a numeração histórica.
- `insumos/contratos_ti_pge.csv` é removido (nunca foi preenchido); `insumos/LEIA-ME.md` e
  `insumos/normas/LEIA-ME.md` generalizados.
- ADR 0001 e ADR 0006 tiveram o contexto generalizado (a decisão em si não mudou) — ver nota em cada uma.
- Decisão D5 (norma estadual de pesquisa de preços do RJ) deixa de ser bloqueante — vira nota opcional em
  `docs/PLANO.md`, já que não há processo formal de nenhum órgão a instruir.
- O volume de dados a ingerir cresce (nacional em vez de um estado) — considerar isso ao dimensionar a
  Fase "Base histórica" (antiga F2).
