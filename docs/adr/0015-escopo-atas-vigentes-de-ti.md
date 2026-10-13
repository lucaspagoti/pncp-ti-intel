# 0015 — Escopo: só atas de registro de preços vigentes, só TI

- Status: aceita (12/10/2026), decisão do Lucas.
- Substitui: ADR 0014 (itens via Dados Abertos). Altera: ADR 0003 (sai "histórico local"),
  ADR 0006 (classificador local vira contingência), ADR 0005 (janela = snapshot do dia).
- **Substituída pela ADR 0016 (13/10/2026):** sai o snapshot `/v1/atas`. Continuam valendo o foco em atas de TI vigentes, a troca atômica de snapshot e a amostra para medir recall.

## Contexto

O desenho anterior baixava o PNCP nacional inteiro (contratações, atas e contratos desde
01/04/2023) para filtrar TI depois. TI é uma fração pequena das compras públicas: mais de 95%
do volume seria descartado. `contratos` sozinho passa de 1,6 milhão de registros em 9 meses e
nem traz preço unitário. O backfill rodou 2h e só cobriu parte de `contratacoes` (82.780
registros). A tentativa de complementar com itens do Dados Abertos abriu uma dúvida de cobertura
nacional sem resposta barata (ADR 0014).

Os usos do projeto não pedem esse volume:
- **Adesão:** depende de atas **vigentes**, não de histórico.
- **Pesquisa de preço:** depende do preço registrado nos itens das atas de TI.
- **Referência de TR/ETP:** depende dos anexos das compras dessas atas.

## Decisão

1. **A base guarda só atas de registro de preços de TI vigentes.** Nada de contratações,
   contratos ou atas vencidas. Não há backfill histórico.
2. **Fonte única: PNCP `/v1/atas`** (volta a valer a ADR 0001 sem exceção). Esse endpoint
   filtra por *sobreposição de vigência*: uma janela de um dia devolve todas as atas vigentes
   naquele dia (484.081 em 12/10/2026, medido por chamada real).
3. **Carga diária = snapshot completo das vigentes.** O PNCP limita a página a 50 itens
   (testado com 500, devolve 50), o que dá ~9.700 páginas, mínimo teórico de ~80 min a 2 req/s (mais latência/retries). É simples e
   correto: o snapshot pega ata nova, alterada e cancelada sem lógica incremental.
   `/v1/atas/atualizacao` existe, mas devolveu só 20 registros em 2 dias e não é a fonte da carga.
4. **Filtro de TI na entrada.** Palavras-chave generosas no `objetoContratacao` (recall
   primeiro). Só as candidatas são gravadas. Para medir recall, cada carga guarda também uma
   amostra aleatória pequena das descartadas, usada só na rotulagem.
5. **Vigência na leitura.** Uma view expõe só atas do snapshot ativo, não canceladas e com
   `vigencia_inicio <= hoje <= vigencia_fim`, usando a data de Brasília (`America/Sao_Paulo`).
   Ata vencida sai da view sem precisar de `DELETE`.
   Ao publicar um snapshot completo, os snapshots anteriores e seus dados são removidos.
6. **Itens e preços só das atas de TI** (próxima entrega da F2). Vêm da compra-mãe de cada ata
   no próprio PNCP, uma consulta por compra. Buscar compra por compra (N+1) é aceitável porque
   N é só o recorte de TI. O endpoint exato e o risco de timeout visto pelo Codex são
   confirmados na implementação.
7. **Classificador local (ADR 0006, camada 2) vira contingência.** Entra só se a rotulagem
   mostrar que palavra-chave + catálogo não atingem as metas D6.

## Consequências

- Volume cai de milhões de registros para o recorte de TI das ~484 mil vigentes. A carga
  diária tem custo fixo e previsível.
- Perde-se a pesquisa de preço em contratações sem ata e o histórico além da vigência. Isso foi
  aceito deliberadamente. Para consulta pontual fora desse recorte, o `compras-mcp` ao vivo
  continua disponível.
- O motor de ingestão da F1 (janelas, upsert, retry, savepoints, log, privacidade, backup) é
  reaproveitado. Os adaptadores e tabelas de `contratacoes`/`contratos` deixam de ser usados e
  saem do código numa migração própria.
- O log detalhado por página das atas TI é retido por 30 dias e limpo no início de cada snapshot;
  os resumos de execução permanecem em `snapshots_atas_ti`.
- A ingestão de itens via Dados Abertos da F2A (migração 0003, `ingest/itens.py`) não segue.
  Reaproveitam-se `classificar/regra.py` (palavras-chave + catálogo) e `classificar/amostra.py`
  (reservoir, CSV que não sobrescreve rótulos).

## Detalhamento da implementação 2A

- Cada execução cria um UUID de snapshot e grava candidatas com chave composta
  `snapshot_id + numeroControlePNCPAta`. A view continua apontando para o último snapshot
  concluído durante a paginação. Só depois da última página, amostra e contagens estarem salvas,
  uma transação troca o snapshot ativo e remove os anteriores. Falha deixa a view anterior intacta.
- Registros repetidos entre páginas são deduplicados por `numeroControlePNCPAta` antes de contar
  ou gravar. A paginação ainda é feita sobre uma fonte mutável; o endpoint não oferece cursor ou
  snapshot consistente entre páginas, então alterações durante a carga podem causar omissões.
- O filtro de entrada exige que a ata esteja dentro da vigência na data consultada e não cancelada;
  para as vigentes, palavras-chave generosas em `objetoContratacao` decidem as candidatas de TI.
  As demais entram em reservoir de até 200 registros por snapshot.
- `make amostra` seleciona até 100 candidatas e até 100 descartadas. O CSV leva tamanho da população
  e da amostra de cada estrato para permitir estimar recall com os pesos corretos.
- A migração 0004 remove os dados da base histórica (contratações, contratos, itens, fornecedores
  e atas antigas). Ela é destrutiva e sem downgrade de dados: exigir backup verificado antes de
  aplicá-la. A migração não foi aplicada ao banco de desenvolvimento durante a implementação.

## Salvaguardas confirmadas na revisão Codex

- Amostra, ativação do snapshot e remoção do anterior são uma única transação. Erros SQL fazem
  rollback antes da limpeza do staging; a exceção original continua identificável.
- Resposta vazia após a primeira página é falha. A paginação percorre pelo menos o maior total
  anunciado pela fonte; uma redução desse total não encerra a carga prematuramente.
- Um snapshot nacional totalmente vazio é tratado como anomalia e não substitui o anterior. Uma
  carga com atas, mas sem candidatas a TI, é válida: pode remover candidatas que mudaram de objeto.
- A migração 0003 permanece apenas para compatibilidade com bancos que já a aplicaram; 0004 remove
  o schema antigo. Não retomar a ingestão de itens via Dados Abertos.
