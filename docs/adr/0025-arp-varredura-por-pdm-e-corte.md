# 0025 — ARP: varredura por PDM de TI e corte de precisão (R2.1)

- Status: aceita (16/10/2026), decisão do Lucas ("seguir com o corte").
- Complementa a ADR 0020 (fonte ARP) e a ADR 0021.

## Contexto

A auditoria de 14/10/2026 mediu recall de 59% por PDM de TI: 5.142 atas vigentes tinham ao menos
um item do CATMAT grupo 70, e a carga só classificava 3.035. O furo vem de a carga buscar itens
apenas das atas cujo **objeto** parece de TI. Mas a lista dos 2.107 "falsos negativos" mostrou que
boa parte é item de TI **incidental** em ata de outro assunto (mouse pad em ata de EPI, impressora
térmica em laboratório de gastronomia, monitor em ata de gás). Marcar a ata inteira como TI por
qualquer item de TI traria ruído; as perdas reais (equipamento de processamento de dados com
notebook e microcomputador, parque tecnológico, manutenção de equipamentos) precisam entrar.

## Decisão

1. **Varredura por PDM** como segunda fonte de candidatas: uma consulta por PDM do grupo 70 e
   janela de 365 dias de início de vigência em `2_consultarARPItem` (`codigoPdm`). A varredura
   é **semanal e retomável**: janelas de 365 dias fixas na semana ISO e um checkpoint por par
   (PDM, janela) em `data/arp/varredura-<ano>-W<semana>.jsonl`. A API chega a 10–30 s por
   consulta, então a carga tem um **orçamento de tempo** (`ARP_VARREDURA_MINUTOS`, padrão 45): o
   que não couber continua na noite seguinte, e uma semana completa não gasta nenhuma
   requisição de varredura nos outros dias. Consulta que falha conta em `varredura_falhas`, não
   derruba a carga e é repetida na noite seguinte (só reduz candidatas enquanto isso).
2. **Corte de precisão** (`insumos/regra_ti_arp.json`, versionado, revisado pelo Lucas): a ata só
   vira TI por itens de catálogo se **≥ 50% dos itens** forem de TI **ou** tiver ao menos um item
   de **PDM central** (toda a classe 7010 de computadores e servidores, mais switch, roteador,
   firewall, impressoras laser/multifuncional/jato de tinta/monocromática e scanner). O
   pré-corte usa `quantidadeItens` da listagem e evita buscar itens das incidentais; o corte final
   usa os itens de fato buscados. O objeto e o anexo da IN 05 continuam valendo primeiro.
3. `motivo_ti` registra a conta: `catmat70:pdm8435@item:central` ou `...:prop2de4`;
   `catalogo_incidental` marca a ata que teve item de TI e não passou no corte.
4. A auditoria (`evals/arp_<data>.md`) passa a medir o recall **pelo critério** (atas que passam no
   corte) e a reportar quantas são incidentais.
5. Os parâmetros ficam em arquivo, e não no código, para poderem ser calibrados com rótulos
   (ADR 0026, curadoria assistida pelo Hermes). Mudar limiar ou lista de PDMs centrais é PR.

## Consequências

- A base ganha as atas de objeto genérico com TI relevante; perde as que só eram TI por item
  incidental. Parte das atas que hoje são TI "pelo catálogo" pode sair (ver o relatório da auditoria).
- Custo: a varredura completa são ~1,3 mil a 2,7 mil consultas, uma vez por semana, repartidas
  em quantas noites o orçamento exigir. Uma ata nova com objeto genérico pode levar até uma semana
  (mais as noites de varredura) para entrar; antes disso ela depende do objeto.
- O limiar 50% e a lista de PDMs centrais são um ponto de partida, não uma verdade: serão
  ajustados com os rótulos do Lucas.
