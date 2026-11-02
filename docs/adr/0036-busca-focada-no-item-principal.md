# 0036 — Busca ordenada pelo item principal da ata

- Status: aceita pelo Lucas (02/11/2026, plano da primeira release da web).
- Altera a `mv_busca_atas` da ADR 0035 e amplia o MVP da ADR 0033 com a linha do item que casou e o
  "você quis dizer".

## Contexto

Em 02/11/2026, o Lucas buscou "monitor" e o primeiro resultado foi uma ata de CFTV. No banco real:

- O radical do português reduz *monitoramento* e *videomonitoramento* a `monitor`, e
  `websearch_to_tsquery('monitor')` casava com 1.514 atas. Só 623 delas tinham *monitor(es)* no
  objeto.
- O `documento` era um vetor único e sem peso (objeto, órgão e todos os itens), ordenado por
  `ts_rank` sem normalização. A ata de CFTV com 154 itens ganhava por repetição.
- No ARP, a descrição do item segue o CATMAT, `NOME DO PDM, atributo, atributo…`. O nome do
  catálogo (PDM) diz o tipo do item. "MICROCOMPUTADOR" cita monitor só nos atributos;
  "MONITOR COMPUTADOR" é um monitor.

Na pesquisa de mercado, a busca de e-commerce resolve o caso "laptop que devolve capas" do mesmo
jeito: identifica o tipo do produto (*head noun*) e **dá peso** a ele, sem filtro rígido. O
Walmart relata um ganho de 4,8% em relevância com o boost por tipo. O Postgres oferece pesos por
campo (`setweight`), `ts_rank_cd` com normalização por tamanho e o dicionário `simple` para a
palavra exata.

## Decisão

- **Cabeça do item.** `mv_busca_itens` guarda um item de TI vigente por linha. A cabeça é o nome
  do catálogo ou, sem ele, a descrição até o primeiro separador (`,` `;` `:` ou ` - `). Ela vai em
  vetor `simple` (palavra exata) e `portuguese` (radical). O texto inteiro do item vai em
  `texto_exato` (`simple`).
- **A recuperação não muda.** O `documento` da 0010 continua sendo o da recuperação. Juntar
  vetores criaria frases falsas na fronteira entre campos: na revisão, `notebook -"notebook
  monitor"` perdia a ata com objeto "Notebook" e item "Monitor". A ordem usa outro vetor,
  `documento_peso`, com objeto em A, cabeças em B e texto completo em C.
- **Nota de relevância** (`consultas.py`, SQL fixo):
  - `2 × foco`, em que foco é a fatia dos itens da ata com a palavra exata na cabeça. Uma ata
    sem itens (busca PNCP) recebe 0,5 quando o objeto traz a palavra exata.
  - `+ 0,5` se o objeto traz a palavra exata.
  - `+ 0,25` se alguma cabeça casa, mesmo só pelo radical.
  - `+ 0,1` se algum item cita a palavra exata no texto.
  - `+ 0,05 × ts_rank_cd(pesos, normalização 1|32)`, só para desempatar. Depois, o vencimento.
- **Palavra exata com plural.** A consulta exata é montada em Python (`web/termos.py`), com as
  formas regulares de singular e plural e só com `[a-z0-9]+`. "monitor" casa com *monitores*,
  mas não com *monitoramento*. O texto do usuário chega ao SQL só como parâmetro.
- **Preço pelo item buscado.** Com termo, a coluna de preço e o filtro de faixa usam os itens que
  casam (pela cabeça ou pela palavra exata no texto). Só quando nenhum item casa valem os da ata
  toda. Item que casa sem preço válido aparece como "sem preço do item buscado" e não passa no
  filtro de faixa.
- **Linha do item que casou.** Cada resultado mostra a cabeça do item com o termo marcado, quantos
  itens casam ("2 de 2 itens") e "do item buscado" junto do preço.
- **Sinônimos revisados.** `insumos/sinonimos_busca.txt` (revisado pelo Lucas, como o
  `termos_ti.txt`) traz grupos que valem quando a busca é exatamente um termo do grupo, com até 3
  alternativas. Exemplos: "headset = fone de ouvido" (o PDM é "FONE OUVIDO") e
  "desktop = microcomputador".
- **"Você quis dizer".** Com zero resultados, `pg_trgm` sobre `mv_busca_vocabulario` (palavras das
  cabeças) sugere até 3 termos.
- **Refresh.** `atualizar_busca()` atualiza itens, atas e vocabulário, nessa ordem, com
  `CONCURRENTLY`. São cerca de 14 s com os dados de 02/11, contra 9 s antes. O `web_reader` lê
  só as views `v_busca_itens` e `v_busca_vocabulario`.

## Avaliação

`uv run python -m pncp_ti.busca_avaliacao` mede a precisão@10 de 20 buscas de TI
(`evals/busca_consultas.csv`). Numa cópia do banco de 02/11 (backup restaurado num Postgres
descartável), a média foi de **43% para 98%**; "monitor" foi de 0% para 100%. Busca e facetas
levaram de 44 a 173 ms.

O juiz é aproximado: uma ata é relevante quando o item de maior valor tem o termo na cabeça. Ele
olha a mesma cabeça que a nota nova, então parte do ganho vem da construção. Por isso o relatório
(`evals/busca_<data>.md`) lista o top 10 de cada busca para conferência humana.

## Consequências

- Migração 0011, reversível. O deploy exige `make backup` e `make migrate`; a migração leva cerca
  de 15 s.
- Busca com várias palavras exige todas na mesma cabeça para contar como foco. Sinônimos novos
  entram pelo arquivo, sem código.
- Fora desta decisão, e dependendo do Lucas: ranking aprendido com cliques, autocompletar e
  correção ortográfica além da sugestão.
