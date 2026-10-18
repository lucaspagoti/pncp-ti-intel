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
   janela de 365 dias de início de vigência em `2_consultarARPItem` (`codigoPdm`). A janela que
   pagina é partida ao meio até caber numa página (a paginação da API perde um registro por
   fronteira, ADR 0021); só uma janela de 1 dia que ainda pagina fica marcada em
   `varredura_incompletas`. A varredura é um **ciclo retomável**: janelas de 365 dias fixas a
   partir do dia em que o ciclo começa e um checkpoint por par (PDM, janela) em
   `data/arp/varredura-<data>.jsonl`, sem seguir links e com modo 0600. A API chega a 10–30 s
   por consulta, então a carga tem um **orçamento de tempo** (`ARP_VARREDURA_MINUTOS`, padrão
   45, valendo também no meio de um par paginado): o que não couber continua na noite seguinte,
   mesmo atravessando a semana. Um ciclo completo não gasta requisição nos dias seguintes e só
   recomeça passados 7 dias. Todo ciclo avança **ao menos um par por noite** (o primeiro par
   ignora o prazo), para que um par lento nunca trave a retomada. O ciclo só vale como completo se todos os pares existem no arquivo
   (um marcador `completa` sozinho, depois de linha truncada, não vale). O cache guarda tudo que a
   API devolve, sem filtrar pelas atas do dia. Consulta que falha conta em `varredura_falhas`,
   não derruba a carga e é repetida na noite seguinte.
2. **Corte de precisão** (`insumos/regra_ti_arp.json`, versionado, revisado pelo Lucas): a ata só
   vira TI por itens de catálogo se **≥ 50% dos itens** (contados por `id_item`, não por linha de
   fornecedor) forem de TI **ou** tiver ao menos um item de **PDM central** (toda a classe 7010 de
   computadores e servidores, mais switch, roteador, firewall, impressoras
   laser/multifuncional/jato de tinta/monocromática e scanner). O objeto e o anexo da IN 05
   continuam valendo primeiro. **Não há pré-corte pela contagem da listagem**: a
   `quantidadeItens` da listagem pode divergir dos itens reais, então toda ata vigente com ao
   menos um item de TI achado pela varredura é candidata e o corte exato roda sobre os itens
   buscados. As incidentais custam a busca de itens uma vez (depois são reaproveitadas da carga
   anterior). Quem já tinha itens na carga anterior continua candidata, então uma varredura
   parcial não derruba TI já classificada.
3. `motivo_ti` registra o item que decidiu e a conta: `catmat70:pdm8435@item:central` ou
   `...:prop2de4`; `catalogo_incidental` marca a ata cujos itens foram buscados e não passaram
   no corte; a carga conta `atas_incidentais`.
4. A auditoria (`evals/arp_<data>.md`) passa a medir o recall **pelo critério** (atas que passam no
   corte) e a reportar quantas são incidentais.
5. Os parâmetros ficam em arquivo, e não no código, para poderem ser calibrados com rótulos
   (ADR 0026, curadoria assistida pelo Hermes). Mudar limiar ou lista de PDMs centrais é PR.

6. **Desistir cedo de par lento** (17/10/2026): na primeira noite um único par deu 7 timeouts de
   90 s e consumiu 36 dos 45 min do orçamento (34 de 1.788 pares feitos). As consultas da
   varredura usam 2 novas tentativas (`TENTATIVAS_VARREDURA`), e não 6; o par que falha volta na
   noite seguinte. O limite do cliente vale também para o 429: três 429 seguidos agora derrubam
   o par (antes eram seis). Aceitável porque a varredura já respeita o limite de taxa e o par
   não gravado no checkpoint é repetido. De dia a API responde em ~2 s: o ciclo inteiro (1.770 consultas) fechou em
   35 min rodando a auditoria sem prazo. De madrugada foram ~20 s por par: com 45 min, um ciclo
   leva cerca de duas semanas de noites. Se a entrada de atas genéricas precisar ser mais
   rápida, a opção é subir `ARP_VARREDURA_MINUTOS` no `.env` (a carga inteira levou 80 min e
   a unit aceita 5 h) ou rodar a auditoria de dia; fica a critério do Lucas.

## Consequências

- A base ganha as atas de objeto genérico com TI relevante; perde as que só eram TI por item
  incidental. Parte das atas que hoje são TI "pelo catálogo" pode sair (ver o relatório da auditoria).
- Custo: a varredura completa são ~1,3 mil a 2,7 mil consultas por ciclo, repartidas em quantas
  noites o orçamento exigir (os PDMs centrais vão primeiro), e a busca de itens das atas novas
  (cerca de 2 mil a mais na primeira vez). Uma ata nova com objeto genérico pode levar até uma semana
  (mais as noites de varredura) para entrar; antes disso ela depende do objeto.
- O limiar 50% e a lista de PDMs centrais são um ponto de partida, não uma verdade: serão
  ajustados com os rótulos do Lucas.
