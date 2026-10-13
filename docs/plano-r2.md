# Plano R2 — Ingestão das atas vigentes do Compras.gov.br (Dados Abertos, módulo ARP)

> Este arquivo é para abrir em outro chat. Estado do projeto em 13/10/2026: R0 mergeada (PR #4), R1
> aberta e pronta para revisão (PR #5: https://github.com/lucaspagoti/pncp-ti-intel/pull/5).
> **Pré-condição:** PR #5 mergeado em `master`; a R2 parte de `master` em `feat/r2-arp`.

## Prompt de abertura (cole no novo chat)

```text
Leia CLAUDE.md, docs/PLANO.md, docs/FASES.md, docs/adr/0016, 0019 e LEIA-ME-CODEX.md. Vamos
executar a R2 (atas vigentes via Dados Abertos ARP). O plano investigado está em
docs/plano-r2.md (cópia de ~/.claude/plans/agile-beaming-torvalds.md). Confirme as decisões
abertas da seção "Decisões abertas", entre em modo plan, atualize o plano com elas e espere minha
aprovação antes de codar. Siga o ciclo do CLAUDE.md (branch própria, testes, revisão por
subagente independente, PR).
```

## Contexto

A R1 cobre só o Estado do RJ (SIGA). A R2 traz a **União e quem compra pelo Compras.gov.br**, com
itens e preço unitário, pela API pública de Dados Abertos (`/modulo-arp`). É a fonte que torna o
produto nacional; a busca PNCP (R3) completa estados e municípios fora do Compras.gov.br.

## O que a API mostrou (chamadas reais, 13/10/2026)

| Fato | Valor | Consequência |
|---|---|---|
| Lista de atas vigentes: `1.2_consultarARP_FimVigencia` (`dataVigenciaFinalMin/Max`, janela ≤ 365 dias) | 148.723 atas hoje→+365d, **298 páginas** de 500; +546 atas em +366→+730d (2 páginas). ~1,3 s por página | **~7 min** para listar todas. Não é o problema do PNCP `/v1/atas` (9,7 mil páginas de 50) |
| Campos da ata | `numeroControlePncpAta`, `numeroAtaRegistroPreco`, `objeto`, `nomeUnidadeGerenciadora`, `nomeOrgao`, `codigoUnidadeGerenciadora`, `dataVigenciaInicial/Final`, `statusAta`, `ataExcluido`, `valorTotal`, `quantidadeItens`, `linkAtaPNCP`, `linkCompraPNCP`, `numeroControlePncpCompra`, `dataHoraAtualizacao` | `linkAtaPNCP` resolve o **link de origem** que o SIGA não tem |
| `statusAta` | `Ata de Registro de Preços` ou `Cancelada`; `ataExcluido` booleano | vigente = não cancelada, não excluída, datas cobrindo hoje |
| Itens em lote: `2_consultarARPItem` (`dataVigenciaInicialMin/Max` ≤ 365 d) | 737 mil + 929 mil linhas, **3.334 páginas**; a 1ª consulta levou 61 s | Varrer tudo é caro (~1 a 2 h) e traz 99% de itens de não-TI |
| Itens por ata: `2.1_consultarARPItem_Id` (`numeroControlePncpAta`) | 0,5 s por ata | Viável **só para as atas candidatas a TI** |
| Itens em lote filtrados: `codigoPdm`, `codigoItem`, `tipoItem` | consulta com `codigoPdm` voltou em 1,5 s | Serve para **auditar recall** pelo catálogo (CATMAT) |
| Campos do item | `numeroItem`, `codigoItem`, `tipoItem` (Material/Serviço), `codigoPdm`, `nomePdm`, `descricaoItem`, `valorUnitario`, `quantidadeHomologadaItem`, `quantidadeHomologadaVencedor`, `quantidadeEmpenhada`, `maximoAdesao`, `niFornecedor`, `nomeRazaoSocialFornecedor`, `classificacaoFornecedor`, `itemExcluido` | Traz **limite de adesão** e **quantidade empenhada**; preço por ata (resolve a dúvida da F2B) |
| Qualidade do `objeto` (1ª página, 500 atas) | 103 começam com "A presente Ata tem por objeto…"; 25 têm termo de TI; tamanho médio 173 caracteres | Texto livre e às vezes genérico: o filtro por objeto perde atas "material de consumo diversos" com item de TI |

Atenção: a 1ª página vem ordenada por fim de vigência, então 5% de TI **não** representa o total.

## Decisão de desenho (recomendada)

**Duas fases por carga, no mesmo padrão atômico da R1 (ADR 0019):**

1. **Listar todas as atas vigentes** (≈ 300 páginas), deduplicar por `numeroControlePncpAta`,
   validar contra `totalRegistros` (a paginação é sobre fonte mutável).
2. **Classificar por objeto** (generoso, recall primeiro) e **buscar itens só das candidatas** por
   `2.1_consultarARPItem_Id`, com limite de taxa e concorrência pequena.
3. **Reclassificar com os itens** (CATMAT/CATSER + nome do PDM + descrição) e publicar tudo numa
   transação, trocando a carga ativa.
4. **Auditoria de recall (uma vez, depois a cada mudança de regra, não diária):** consultar o
   endpoint de itens por `codigoPdm` para os PDMs de TI do CATMAT (grupo 70) e achar atas com item
   de TI que o objeto não pegou. É a única medida de recall não circular disponível para federal.

**Não generalizar `ingest/executar.py`** (contra o que a R0 escreveu em FASES): ele grava e faz
commit por página, o oposto do padrão atômico da R1. Construir `fontes/arp.py` no padrão da R1 e
**remover** `ingest/executar.py`, `windows.py`, `log.py` e seus testes (código morto desde a R0).
Manter `ingest/rate_limit.py`. Registrar em ADR.

## Modelo de dados (migração `0006`)

Reusa `cargas`, `atas`, `ata_itens`, `atas_vistas`. A tabela `atas` hoje tem a forma do SIGA
(status `Válida`, `processos[]`), então:

- `atas`: + `vigente_na_origem boolean NOT NULL` (SIGA: status `Válida`; ARP: não cancelada e não
  excluída), `numero_controle_pncp`, `link_origem`, `orgao`, `valor_total`, `quantidade_itens`.
  Backfill das linhas do SIGA. As views passam a usar `vigente_na_origem` no lugar do literal
  `'Válida'`.
- `ata_itens`: + `tipo_item`, `codigo_catalogo`, `codigo_pdm`, `nome_pdm`, `cnpj_fornecedor`
  (CPF mascarado/identidade HMAC via `privacy.identificar_fornecedor`), `quantidade_empenhada`,
  `maximo_adesao`.
- Mapeamento ARP → `atas`: `id_origem = numeroControlePncpAta`; `numero = numeroAtaRegistroPreco`;
  `unidade_gerenciadora = nomeUnidadeGerenciadora`; `licitacao = numeroCompra/anoCompra`.
- Chave do item: hash **do texto mascarado** (lição do B1 da R1), nunca da linha bruta.
- `fonte = 'compras_arp'`. Views unificadas entre fontes ficam para depois da R3.

## Critério de TI (decisão aberta, ver abaixo)

O anexo da IN PRODERJ 05/2024 é norma **estadual do RJ**; estendê-lo à União é decisão sua. Proposta:
união de (a) regra do anexo aplicada a objeto e itens (`classificar/in05.py`, reutilizada) e (b) o
catálogo: CATMAT grupo 70 e as classes CATSER já confirmadas em `classificar/regra.py`
(`classificar_por_regra`). O `motivo_ti` registra qual regra decidiu. Itens CATSER pendentes
(telefonia/internet) seguem o que o anexo diz: TI.

## Validações e idempotência

- Contrato de campos (`campos_esperados` do `compras-mcp` como referência): falha se sumirem
  `numeroControlePncpAta`, `valorUnitario`, `niFornecedor`.
- Pisos contra a carga ativa: atas ≥ 50%; itens ≥ 70%; atas candidatas sem item ≤ 5%.
- `totalRegistros` somado nas páginas ±1%; página vazia no meio é falha; `dataVigenciaFinal`
  fora de [hoje, hoje+730d] é anomalia.
- Sem arquivo para hashear: detectar "sem mudança" pelo hash de `(numeroControlePncpAta,
  dataHoraAtualizacao)` ordenado + versão da regra.
- Falha em qualquer etapa registra em `cargas` e mantém a carga anterior (padrão da R1).
- Cliente: `compras_mcp.clients.dados_abertos.DadosAbertosClient.list_resource` (retry e timeout
  já existem), com `LimitadorTaxa` do projeto; teto de requisições por execução configurável.

## Arquivos

- Novos: `src/pncp_ti/fontes/arp.py`, `src/pncp_ti/fontes/arp_dados.py` (mapeamento e validação
  puros), `db/migrations/versions/0006_arp.py`, `docs/adr/0020-fonte-arp-compras-gov.md`,
  `tests/test_arp_*.py`, `tests/test_migration_0006.py`, fixtures sintéticas em `tests/arp_dados.py`.
- Alterados: `Makefile` (`ingest FONTE=arp`), `classificar/in05.py`/`regra.py` (reuso, sem
  mudar comportamento do SIGA), views do SIGA (predicado `vigente_na_origem`), docs.
- Removidos: `ingest/executar.py`, `ingest/windows.py`, `ingest/log.py` e testes de
  paginação/janelas; tabela `log_execucao_ingestao` (migração).

## Passos

0. PR #5 mergeado; `git checkout master && git pull`; branch `feat/r2-arp`.
1. Confirmar as decisões abertas; ADR 0020.
2. Migração 0006 + teste (backup restaurado antes de aplicar no banco local).
3. `arp_dados.py` (mapeamento, validação, chave mascarada) com TDD e fixtures sintéticas.
4. `arp.py`: listagem paginada, candidatas, itens por ata com taxa, publicação atômica, CLI.
5. Carga real; contagens contra `totalRegistros`; conferência manual de 10 atas contra o
   `linkAtaPNCP`.
6. Auditoria de recall por PDM e relatório em `evals/arp_<data>.md`.
7. Revisão por subagente independente (segurança + critério de aceite), PR.

## Verificação (critério de aceite)

- `make test` verde, incluindo: paginação com duplicata entre páginas, página vazia, campo
  ausente, queda de volume, falha no meio (rollback), CPF de fornecedor PF mascarado e fora da
  chave, mudança de regra reclassificando, permissões do leitor nas views.
- Carga real: nº de atas = soma de `totalRegistros` das duas janelas (±1%); duas execuções seguidas
  sem duplicar; tempo total medido (meta: < 30 min).
- 10 atas sorteadas conferem com o `linkAtaPNCP`.
- Relatório de recall por PDM com os falsos negativos listados. **Não** declarar recall nacional
  sem ele.

## Decisões abertas (confirmar no novo chat)

1. **Critério de TI para atas federais/municipais:** só o anexo da IN 05 (RJ), ou a união
   anexo + CATMAT grupo 70 / CATSER (recomendado)?
2. **Remover `ingest/executar.py` e correlatos** (recomendado) em vez de generalizá-los?
3. **Itens só das candidatas** (recomendado, ~20 min) ou carga completa de itens (1 a 2 h)?
   A completa dá recall perfeito por item e custa 100x mais.
4. **Cadência:** uma carga por dia (recomendado). A API não tem janela incremental confiável.

## Riscos

| Risco | Mitigação |
|---|---|
| Objeto genérico esconde ata com item de TI | Auditoria por PDM; se o recall for baixo, ampliar candidatas por `nomePdm` de TI e por `quantidadeItens` |
| API lenta ou com bloqueio sob carga | Taxa baixa, concorrência ≤ 4, retry do cliente, teto por execução, falha preserva a carga |
| Paginação sobre fonte mutável omite ata durante a carga | Validar `totalRegistros`; reexecutar; aceitar e medir a perda |
| Anexo do RJ aplicado à União | Decisão 1 explícita; `motivo_ti` mostra a regra |
| Preço de ata de TI de serviço (mensal, por usuário) não é comparável | Fora do R2 (normalização de unidades segue no backlog) |
