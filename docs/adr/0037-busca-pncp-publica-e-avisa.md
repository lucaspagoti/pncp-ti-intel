# 0037 — Busca PNCP publica com termo defasado e avisa; retry para a queda do portal

- Status: aceita pelo Lucas (09/11/2026, plano R3.1).
- Altera a ADR 0028 (o limite de 3 dias deixa de derrubar a carga) e as ADRs 0023 e 0030
  (retry da busca e alerta das 08:30).

## Contexto

De 05/11 a 09/11/2026 a busca PNCP não publicou: a carga falhava todo dia com
`termos_falhos`, porque um termo ("materiais de informatica") estava pendente desde 02/11 e a
ADR 0028 derruba a carga inteira no 3º dia. Os outros 56 termos ficaram sem atualizar junto. Em
09/11 já eram 4 termos pendentes. É a mesma crise de 18/10 que originou a ADR 0028.

Medições de 06/11/2026, só leitura:

- `pncp.gov.br/api/search/` derrubou a conexão antes de responder em 60–65% das requisições de
  curl e httpx: 12/20 e 13/20 com 0,5 s e 3 s entre requisições, 7/10 com HTTP/1.1 ou HTTP/2,
  8/12 com User-Agent descritivo e Referer. A home `/app/` também (6/10). Não é ritmo nem
  volume nosso: é o portal com clientes que não são navegador.
- A queda é instantânea (0 s). O retry de 6 tentativas com backoff de 2 a 32 s gastava até 1 min
  por página sem ganho: com 65% de queda, uma página esgota as 6 tentativas em 7,5% das vezes, e
  um termo de 20 páginas perde a passada em ~78% das noites.
- A API oficial de consultas (`/api/consulta/v1/atas/atualizacao`) respondeu 9/9 no mesmo
  horário, com 429 só em rajada. Ela é o assunto da ADR 0038 (coletor incremental).
- Imitar cabeçalhos de navegador foi descartado: é frágil, contorna uma barreira do portal e a
  rota oficial não precisa disso.

## Decisão

1. **Publica e avisa.** Termo pendente continua reaproveitando as atas da carga ativa que casam
   o termo (ADR 0028). Com `DIAS_PENDENTE` (3) dias ou mais ele vai para
   `contagens.termos_defasados` (`{termo: data da primeira falha}`), e a carga publica.
2. **Teto.** A carga só falha (`termos_falhos`, saída 1, `OnFailure`) quando um termo está
   pendente há `DIAS_TETO_PENDENTE` (14) dias ou mais.
3. **Aviso das 08:30.** A operação diz numa frase, junto dos demais avisos do dia (ADR 0030):
   "a busca PNCP está com N termos sem atualizar há X dias (portal instável)", com X do termo
   mais antigo, enquanto houver termo defasado na carga ativa.
4. **Retry por tipo de falha.** Até 12 tentativas por página. Conexão derrubada antes de
   qualquer resposta (`reset`) tenta de novo em 0,5–2 s; timeout, corpo cortado no meio, JSON
   inválido, 429 e 5xx usam backoff exponencial de 2 s com teto de 30 s. Até 4 passadas extras,
   5 min depois da anterior, e nenhuma começa depois de 90 min de coleta
   (`orcamento_esgotado`).
5. **Telemetria** em `cargas.contagens` e no log `pncp_busca_rede`: `requisicoes`,
   `falhas_por_tipo`, `taxa_falha`, `falhas_por_termo` (só termos com falha) e `passadas_extra`.
6. **Nova tentativa no script.** `carga_diaria.sh` repete uma vez, 30 min depois, o SIGA ou a
   busca PNCP que sair com código 1, se a carga estiver abaixo de 3h30 (a unit para em 5h). O ARP
   não é repetido (leva mais de 2 h). Código 2 continua sem nova tentativa.

## Consequências

- Um termo instável deixa de parar a fonte. As atas dele podem ficar até 14 dias sem
  atualização (ata nova não entra; a cancelada continua), com aviso diário a partir do 3º dia.
- O aviso das 08:30 se repete enquanto o termo estiver defasado: é um problema real e
  contínuo, não uma repetição da mesma falha (ADR 0030).
- `MOTIVOS["termos_falhos"]` passa a dizer "há 14 dias".
- Sem migração: tudo cabe em `cargas.contagens`.
