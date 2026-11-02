# 0035 — Busca materializada, atualizada depois de cada carga

- Status: aceita pelo Lucas (02/11/2026, plano do MVP funcional).
- Altera a `v_busca_atas` da migração 0008 (ADR 0023).

## Contexto

Em 02/11/2026, com 20.625 atas vigentes, a busca "notebook" levava 4,8 s (3,7 s no Postgres)
contra um `statement_timeout` de 8 s. A `v_busca_atas` recalculava `to_tsvector` e agregava 94
mil itens a cada requisição. As contagens por filtro do MVP (ADR 0033) multiplicariam esse
custo por página.

No mesmo dia, uma busca respondeu 500 com `AdminShutdown`: o Postgres tinha reiniciado e o pool
da web entregou uma conexão morta.

## Decisão

- **Busca materializada.** `mv_busca_atas` guarda o conteúdo da antiga `v_busca_atas`, com o
  `tsvector` pronto (`documento`), índice GIN e índice único `(fonte, id_ata)`.
- **Vigência por cima da MV.** `v_busca_atas` lê a MV e reaplica o filtro de vigência com a data
  de hoje (`America/Sao_Paulo`). Assim, a ata que vence à meia-noite sai da busca sem esperar a
  próxima carga. Uma ata cujo início cai depois do último refresh só aparece no refresh
  seguinte.
- **Refresh por carga.** Cada fonte chama `atualizar_busca()` ao terminar com sucesso, inclusive
  com `sem_mudanca` e em carga manual.
  - É uma função `SECURITY DEFINER` com `REFRESH ... CONCURRENTLY`, que não bloqueia as buscas
    em andamento. O papel `ingest` pode executá-la; o `web_reader`, não.
  - Leva cerca de 9 s com os dados de hoje.
  - Se o refresh falhar, a carga continua publicada e a web segue com a busca anterior, que é
    consistente. O processo sai com código 1, o `OnFailure` da carga avisa, e
    `make refresh-busca` refaz o refresh manualmente.
- **Rodapé.** `v_cargas_web` dá ao `web_reader` a data de referência de cada carga ativa.
- **Pool resistente.** O pool da web testa a conexão antes de entregá-la (`check_connection`).
  O `/saude` consulta o banco e responde 503 quando ele cai.

## Consequências

- Na cópia de produção, a página de busca com as facetas leva de 40 a 80 ms, contra cerca de
  4,5 s antes.
- Entre a troca da carga e o fim do refresh (segundos), a busca mostra a carga anterior,
  enquanto o detalhe e os itens (views ao vivo) já mostram a nova. Uma ata que saiu da carga
  nova dá 404 no detalhe nesse intervalo.
- Migração que recriar `v_atas_ti_vigentes` precisa derrubar e recriar `mv_busca_atas`.
- O stemmer `portuguese` não reduz "notebooks" a "notebook". A busca por "notebook" acha a ata
  pelos itens e pelo objeto no singular, e isso já era assim antes desta ADR.
