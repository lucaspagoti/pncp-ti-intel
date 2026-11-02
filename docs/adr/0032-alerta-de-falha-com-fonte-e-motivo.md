# 0032 — Alerta de falha da carga diz a fonte e o motivo

- Status: aceita pelo Lucas (02/11/2026).
- Altera a ADR 0030 (texto do `OnFailure` da `pncp-ti-carga.service`).

## Contexto

De 29/10 a 02/11/2026 o Lucas recebeu todo dia "Atas de TI: a atualização de hoje falhou; o
site segue com os dados anteriores." e não tinha como saber qual fonte falhou nem por quê. A
causa (SIGA RJ, ADR 0031) só apareceu no journald.

## Decisão

- No `OnFailure` da carga, `operacao falha` lê a última carga de hoje de cada fonte em
  `cargas` (`connect_timeout=5`) e monta uma frase só, com as fontes que falharam e o motivo
  traduzido de `erro_tipo` (`MOTIVOS`). Exemplo: "Atas de TI: o SIGA RJ não atualizou hoje
  (arquivo fora do padrão); o site segue com os dados anteriores." Com duas fontes: "o SIGA RJ
  (arquivo fora do padrão) e a busca PNCP (portal sem responder alguns termos há 3 dias) não
  atualizaram hoje; …".
- Tipo desconhecido sai sem o parêntese. Classes de exceção de rede (`*Timeout`,
  `ConnectError`, `Compras*`) viram "fonte fora do ar".
- Com o banco fora ou sem carga falha registrada hoje, sai a frase genérica da ADR 0030. O
  `OnFailure` continua avisando com o Postgres indisponível.
- Os outros serviços (web, backup, operação) mantêm a frase da ADR 0030.

## Consequências

- Continua sendo uma mensagem por falha noturna, agora dizendo onde olhar.
- Uma fonte que falha antes de gravar em `cargas` (por exemplo, trava concorrente) não aparece
  na frase; se nenhuma aparecer, sai a frase genérica.
- `erro_tipo` novo nas fontes deve ganhar uma entrada em `MOTIVOS`, ou sai sem motivo.
