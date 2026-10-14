# 0020 — Fonte ARP do Compras.gov.br: carga atômica, critério de TI composto e limpeza

- Status: aceita (13/10/2026). Decisões do Lucas na rodada de perguntas da R2 (13/10/2026).
- Corrigida pela ADR 0021 (14/10/2026): atas sem número PNCP, ids repetidos, listagem
  adaptativa e tempos medidos.
- Detalha: ADR 0016 (fontes), 0019 (padrão de carga atômica) e 0017 (agendamento).
- Substitui, no que toca à R2: a previsão de "generalizar `ingest/executar.py`" em `docs/FASES.md`.

## Contexto

A R1 cobre só o Estado do RJ. A R2 traz a União e quem compra pelo Compras.gov.br pela API
pública de Dados Abertos (`/modulo-arp`), com itens, preço unitário e limite de adesão. Medidas
de 13/10/2026: 148.723 atas com fim de vigência de hoje a +365 dias (298 páginas de 500, cerca de
1,3 s por página), mais 546 em +366 a +730 dias. Itens em lote custam 3.334 páginas e 99% não são
de TI; por ata custam cerca de 0,5 s.

## Decisão

1. **Mesmo padrão da R1.** Lista → classifica → grava numa carga nova e troca a ativa numa única
   transação (`fontes/arp.py`). Trava consultiva de sessão e de transação, pisos contra a carga
   ativa (atas ≥ 50%, itens ≥ 70%), falha registrada em `cargas` só com tipo e SQLSTATE, e a
   carga anterior continua visível.
2. **Listagem sem paginar.** A paginação da API não tem desempate estável: numa janela de duas
   semanas, 682 de 6.979 registros vieram repetidos e outros 682 nunca vieram, e o resultado se
   repete idêntico em nova consulta (13/10/2026). A primeira coleta real perdeu 3.956 de 149.276
   atas (2,7%). Por isso cada janela de `1.2_consultarARP_FimVigencia` é dividida ao meio até
   caber numa página (≤ 500): primeiro pelo fim da vigência e, num dia cheio (01/12/2026 tem 834
   atas), por `dataAssinaturaInicial/Final`. Se a soma das metades não bate com o total (ata sem
   data de assinatura), a janela é paginada e contada em `janelas_paginadas`. Dedupe por
   `numeroControlePncpAta` e conferência de `totalRegistros` (±1%) logo após a listagem, antes de
   gastar cota com itens. Página vazia no meio é falha. Fim a mais de 1.100 dias é anomalia.
3. **Itens só das candidatas, reaproveitando os que não mudaram** (decisão do Lucas). Candidata =
   objeto com sinal de TI pela regra do anexo **ou** pela lista generosa de `classificar/regra.py`
   (6.155 em 13/10/2026). A API limita a cerca de 100 requisições por minuto e responde 429 com
   espera de 36 s; por isso a taxa é 1,5 por segundo (`ARP_REQUESTS_PER_SECOND`), concorrência 2,
   até 6 tentativas e teto de 20.000 requisições (`ARP_MAX_REQUISICOES`). Os itens de uma ata cuja
   `dataHoraAtualizacao` não mudou são copiados da carga ativa; cada ata ainda tem um dia fixo da
   semana em que os itens são rebuscados, porque o item pode mudar sem a ata mudar. A primeira
   carga busca tudo (cerca de 1 h); as diárias buscam as novas, as alteradas e 1/7 das demais.
   Candidatas sem item acima de 5% falham a carga.
4. **Critério de TI composto** (decisão do Lucas): anexo da IN PRODERJ 05/2024 aplicado a objeto e
   nome do PDM **ou** catálogo (CATMAT grupo 70 por PDM; serviços das classes CATSER de
   `classificar/regra.py`). O anexo decide primeiro; o catálogo só acrescenta atas sem nenhum
   sinal do anexo, e **nunca reverte** exclusões explícitas (nobreak, drone). O `motivo_ti`
   registra a regra: `catmat70:pdm239@item`, `catser8713:servico1260@item` ou o motivo do anexo.
   O anexo é norma estadual do RJ; estendê-lo à União é decisão do Lucas, registrada aqui.
5. **Limite conhecido de recall.** Ata com objeto genérico e sem termo de TI não é candidata, e
   portanto seus itens não são buscados. A auditoria por PDM (itens de TI no endpoint em lote,
   `codigoPdm`) mede esse furo e vai para `evals/arp_<data>.md`. Não declarar recall nacional sem
   ela.
6. **Sem atalho de "sem mudança".** Toda execução lista tudo e publica uma carga nova; só a busca
   de itens é incremental (item 3). A idempotência vem da troca atômica.
7. **Privacidade.** CPF de fornecedor PF fica fora da chave e do banco: a identidade é HMAC
   (`privacy.identificar_fornecedor`) e a chave do item usa o identificador mascarado, o mesmo
   cuidado da correção B1 da R1. Texto livre passa por `sanitizar`.
8. **Modelo.** Migração 0006: `atas.vigente_na_origem` (SIGA: `Válida`; ARP: não cancelada e não
   excluída), link de origem, órgão, valor, quantidade de itens; `ata_itens` com tipo, códigos
   de catálogo, quantidade empenhada e limite de adesão. As views usam `vigente_na_origem`.
9. **Limpeza.** Removidos `ingest/executar.py`, `windows.py`, `log.py`, os testes de paginação e
   a tabela `log_execucao_ingestao`: gravavam e faziam commit por página, o oposto do padrão
   atômico, e ficaram sem uso desde a R0. Mantido `ingest/rate_limit.py`.

## Consequências

- A primeira carga leva cerca de 1 h; as diárias, a listagem mais os itens das atas novas,
  alteradas e do dia de renovação. A listagem por bissecção custou 41 min na 1ª carga real
  (não 10 min); os tempos da listagem adaptativa estão na ADR 0021 e na PR.
- Preço por ata fica disponível (resolve a dúvida da F2B), com limite de adesão e empenho.
- Atas de TI com objeto genérico podem escapar até a auditoria por PDM; o `motivo_ti` e o
  relatório de recall tornam o furo visível, e não escondem.
- Preço de serviço de TI (mensal, por usuário) segue sem normalização de unidade (backlog).
