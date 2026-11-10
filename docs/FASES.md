# Fases do projeto

Cada fase começa só quando a anterior cumpre o critério de aceite. O roadmap foi refeito em
13/10/2026 (ADRs 0016, 0017 e 0018): as fases F2 a F7 do desenho PNCP/MCP foram substituídas pelas
fases R0 a R6 abaixo. F0 e F1 ficam como histórico.

Prompt-padrão de abertura (substitua N e cole o bloco da fase):

```
Leia CLAUDE.md, docs/PLANO.md e docs/adr/ (principalmente 0016, 0017 e 0018). Vamos executar a fase RN.
<bloco da fase abaixo>
Antes de codar: verifique o que o compras-mcp (como biblioteca) e as bibliotecas existentes já resolvem,
proponha o plano da fase em modo plan e espere minha aprovação.
```

---

## Histórico

**F0 · Fundação: ✅ concluída** (13/10/2026, tag `f0-fundacao`). Repositório, `uv`, Docker Compose,
CI com lint/testes/segredos, pre-commit.

**F1 · Infraestrutura de ingestão: ✅ mergeada** (PR #2). Motor idempotente (retry/backoff,
savepoints, log), papéis `ingest`/`mcp_reader`, privacidade de fornecedor (ADR 0013), backup e
restauração em banco novo.

**F2 · Atas de TI vigentes via PNCP: encerrada sem aceite** (ADR 0016). A F2A (snapshot
`/v1/atas` com filtro de TI) foi mergeada no PR #3 (`df301c3`). A migração 0004 foi aplicada ao banco
local depois de um backup restaurado com sucesso. Duas tentativas de snapshot nacional (cerca de
484 mil atas, 9.682 páginas de 50) falharam ou foram canceladas, e nenhuma versão foi publicada. O
piloto da F2B achou as compras-pai, mas `/itens` em `/api/consulta` deu 404 em três casos. O
desenho foi substituído pelas três fontes da ADR 0016. Ficaram do trabalho: o motor de retry
(`a1fc870`), a regra de TI, a amostra para rotulagem e o padrão de troca atômica de snapshot.

---

## R0 · Replanejamento

**Entregas**
- ADRs 0016 (fontes), 0017 (orquestração) e 0018 (web); status atualizado nas ADRs afetadas.
- `PLANO.md`, `FASES.md`, `CLAUDE.md`, `README.md` e `LEIA-ME-CODEX.md` reescritos.
- Remoção do adaptador `/v1/atas` (`ingest/atas.py`, `cli.py`, `mapeadores.py`, `client.py`), do
  `.mcp.json` e dos testes do servidor `compras-mcp` e da fumaça PNCP.

**Critério de aceite**
- `make test` verde; documentação consistente entre si.

**Status:** concluída (as fases R1 a R6 partem deste replanejamento).

## R1 · Ingestão SIGA RJ

**Entregas** (ADR 0019)
- `fontes/siga.py` + `fontes/siga_csv.py`: download dos 3 CSVs (timeout, limite de 100 MB,
  sha256, `Last-Modified`, retry), validação estrita, colapso de processos, dedupe por conteúdo,
  carga numa transação e troca atômica. `make ingest FONTE=siga`.
- Migração `0005`: `cargas`, `atas`, `ata_itens`, `ata_participantes`, `atas_vistas` e as views
  `v_atas_ti_vigentes`, `v_ata_itens_ti`, `v_ata_consumo_item`. Aplicada ao banco local depois de
  backup restaurado em banco temporário.
- `classificar/in05.py`: regra de TI pelo Anexo Único da IN PRODERJ/PRE 05/2024.
- `make amostra` (censo das atas vigentes para rotular) e `make eval ROT=...` (precisão/recall
  contra o rótulo final, em `evals/`).

**Critério de aceite**
- Reprocessar os mesmos 3 CSVs mantém contagens e registros, sem duplicação. ✅ (teste e carga
  real: a segunda execução registrou `sem_mudanca`)
- Falha de validação, de download ou de gravação preserva a carga anterior e fica em `cargas`. ✅
  (testes) Itens ou participantes abaixo de 70% da carga ativa não publicam. ✅ (teste)
- Revisão independente concluída e achados tratados (ADR 0019, seção "Revisão independente"). ✅
- Conferência manual de 10 atas contra o CSV bruto. ✅ (10 de 10, 13/10/2026)
- `v_atas_ti_vigentes` lista as atas de TI vigentes do RJ com itens e preço unitário. ✅ (24 atas
  em 13/10/2026) Conferência manual de 10 atas contra o CSV bruto: ✅ 10 de 10.
- Precisão e recall medidos contra o rótulo final (D6; meta: recall ≥ 95%, precisão ≥ 85%). ✅
  100% e 100% sobre o censo de 1.574 atas (`evals/siga_20261013.md`). **Ressalva:** o rótulo foi
  aplicado pelo Claude, por instrução do Lucas, seguindo o anexo da IN 05 literalmente; regra e
  rótulo usam o mesmo anexo, então não é um recall independente. Decidido em 13/10/2026: seguir o
  anexo, inclusive telefonia, pontos de rede e videomonitoramento.
- Link de origem: processo SEI + CSV de origem. O SIGA não tem URL pública por ata conhecida.

**Status:** concluída (PR #5 e #6 mergeados em 13/10/2026).

## R2 · Ingestão Dados Abertos ARP

**Entregas** (ADR 0020)
- `fontes/arp.py` sobre o `DadosAbertosClient` do `compras-mcp`: atas vigentes em três janelas de
  365 dias (`1.2_consultarARP_FimVigencia`), itens só das candidatas (`2.1_consultarARPItem_Id`),
  critério de TI composto (anexo da IN 05 ou catálogo CATMAT 70/CATSER) e troca atômica.
- Migração 0006 (`vigente_na_origem`, campos da ARP) e remoção do ingestor legado por página.
- Timer systemd diário às 03:00 (`deploy/systemd/`, `scripts/carga_diaria.sh`), SIGA e ARP
  independentes, com ping opcional no Uptime Kuma.

**Critério de aceite**
- Idempotência; atas = `totalRegistros` (±1%); amostra de 10 atas conferida contra o
  `linkAtaPNCP`; itens com preço unitário; relatório de recall por PDM em `evals/`.

**Resultado (14/10/2026):** 1ª carga real com 146.134 atas listadas contra 148.575 declaradas
(as 2.515 sem identificador do PNCP ficam fora, ADR 0021), 6.161 atas de TI vigentes e 22.636
itens. Conferência de 10 atas contra o PNCP: 10/10 em vigência, situação e preço. Recall por PDM
de TI: **59%** (3.035 de 5.142 atas com item do grupo 70); o furo são atas com objeto genérico
que não viram candidatas (`evals/arp_20261014.md`). Timer diário instalado no homelab (03:00).

**Status:** concluída (PR #7).

## R2.1 · Varredura por PDM e corte de precisão

**Entregas** (ADR 0025)
- `varrer_pdm` em `fontes/arp.py`: segunda fonte de candidatas, em ciclo retomável com orçamento
  de tempo (a API é lenta nas consultas por PDM). Ata nova de objeto genérico pode levar até
  uma semana para entrar.
- `insumos/regra_ti_arp.json` + `fontes/arp_regra.py`: ata só vira TI por itens de catálogo se
  ≥ 50% dos itens forem de TI ou tiver PDM central; `catalogo_incidental` marca o resto.
- Auditoria mede o recall pelo critério.

**Critério de aceite**
- Testes verdes e carga real com o corte; relatório em `evals/` com recall pelo critério e a
  contagem de incidentais; Lucas revisa a lista de PDMs centrais.

**Status (19/10/2026):** decisões pendentes tomadas pelo Lucas (ADR 0025, item 7).
- A proporção agora é calculada **por compra**, somando as atas de todos os fornecedores.
  Também passa a ata com ≥ 2 itens de TI.
- A lista de 34 PDMs centrais foi aprovada.
- A varredura usa a madrugada até as 06:00 (`ARP_VARREDURA_MINUTOS=90` no `.env`).

Na reclassificação somente leitura da carga ativa, as atas de TI vigentes vão de 7.723 para
7.387: saem 412 só-proporção e entram 76 com ≥ 2 itens.

Falta para o aceite: a carga real com o corte novo e o relatório `evals/arp_<data>.md`.

Histórico (17/10/2026): mergeada (PR #13) e com carga real.
- A primeira noite fez só 34 de 1.788 pares: um par deu 7 timeouts e gastou o orçamento. A
  varredura agora desiste depois de 2 novas tentativas (ADR 0025, item 6).
- O ciclo foi fechado de dia pela auditoria. A carga `4ee904bf` publicou 7.762 atas de TI
  vigentes (eram 6.222), com 343 incidentais e recall pelo critério de 100%
  (`evals/arp_20261017.md`).

## R3 · Busca PNCP por termos de TI

**Entregas**
- `insumos/termos_ti.txt` (versionado; o Lucas revisa).
- `fontes/pncp_busca.py`: uma consulta por termo, com paginação de 500, retry e dedupe por
  `numero_controle_pncp` (o ARP tem preferência na view).
- Teste de contrato que falha alto se os campos mudarem (marcado como teste de rede).

**Critério de aceite**
- A busca de um termo conhecido bate com o portal; nenhuma duplicata com o ARP na view.
- Avaliar cobertura com referências independentes dos resultados da lista de termos (D6);
  registrar limites da amostra sem alegar recall nacional não demonstrado.

**Status (19/10/2026):** concluída (ADR 0023, 0028, migração 0007; `evals/pncp_busca_20261017.md`).
- Termo conhecido: `notebook` no portal aceita 132 atas, e a carga ativa tem 130, todas em comum. ✅
- Nenhuma duplicata com o ARP na view: 21.038 linhas com `numero_controle_pncp`, 21.038 distintas. ✅
- Cobertura contra o ARP (referência independente, só na sobreposição SIASG/PNCP): 47,2%, com
  os limites registrados. Não há alegação de recall nacional. ✅
- Precisão rotulada: 30 de 30 na amostra só-busca, com 3 mistas contadas como TI (decisão do
  Lucas); rótulo do Claude conferido pelo Lucas. ✅
- Lista revisada pelo Lucas em 19/10: sai `gestao de documentos`, `impressora` e `toner` ficam
  com ruído aceito, e a última palavra do termo aceita só plural (corrige `tablet` → "tablete"). ✅
- Termo que o portal não responde reaproveita a carga ativa por até 3 dias (ADR 0028, PR #21).
- R3.1 (09/11/2026, ADR 0037): o portal derruba ~60% das conexões de script; o termo pendente
  passa a defasado aos 3 dias (a carga publica e a operação avisa) e só derruba a carga aos 14.
  Retry curto para queda instantânea, telemetria de rede em `cargas.contagens` e nova tentativa
  da busca no `carga_diaria.sh`. Próximo passo: coletor incremental pela API oficial (ADR 0038).
- R3.1 PR 2 (ADR 0038): coletor `pncp_atas` pela API oficial de consultas, na mesma fonte e nas
  mesmas views. Delta diário por `/v1/atas/atualizacao` (33 s e 8 requisições em 09/11) e
  varredura mensal aditiva de `/v1/atas` em unit própria, com checkpoint (6h40 na primeira).
  Contra a busca ativa: 99,5% em comum e 1.398 atas a mais (`evals/pncp_atas_20261109.md`). A
  busca do portal virou reserva automática no `carga_diaria.sh`, com aviso `pncp:reserva`.

Em aberto, a critério do Lucas: `informatica` sozinha e `tic`/`ti` (cerca de 1.500 atas perdidas
contra o ARP), que exigem regra melhor ou curadoria (ADR 0026).

## R4 · Web local

**Entregas**
- `web/` (FastAPI + Jinja2 + HTMX), servida em `127.0.0.1`.
- Busca por objeto/item; filtros por fonte, esfera, UF, órgão, "vence até" e faixa de preço.
- Detalhe da ata: itens, fornecedor, preço unitário e participantes/saldo (SIGA), com link de
  origem.
- Exportação CSV com fórmulas neutralizadas; autoescape.
- Papel `web_reader` (só views). Testes com `TestClient` e de permissão.

**Critério de aceite**
- O Lucas pesquisa "outsourcing de impressão", "notebook" e "licença Microsoft" e vê atas vigentes
  federais, estaduais (incluindo RJ) e municipais, com preços quando a fonte traz itens.

**Status (16/10/2026):** implementada em `feat/r4-web` (ADR 0023, migração 0008, `make web`). Com os
dados reais, as três buscas devolvem 325, 58 e 81 atas em ~1,5 s. Falta o Lucas fazer a
demonstração dele. Limite conhecido: esfera e UF não existem para as atas do ARP.

A nova interface e o QA executor seguem o roadmap próprio, `docs/ROADMAP-WEB.md` (W0–W2,
ADR 0029); o aceite da R4 é o da W2.

## R5 · Exposição no domínio

**Entregas**
- Decisão D7. Cloudflare Tunnel + Access e Caddy com autenticação na frente da web; Postgres
  continua em loopback.
- Checklist OWASP Top 10 (web).

**Critério de aceite**
- Acesso externo funciona só com credencial e recusa sem ela.

**Status (02/11/2026):** o Lucas escolheu a opção A da ADR 0024: `atas.myhomelablp.site` pelo
Cloudflare Tunnel, com o Access (só o e-mail dele) e o `basic_auth` do Caddy na frente. O Caddy
recebe o tunnel em `127.0.0.1:8444`. Passo a passo em `deploy/caddy/README.md`, checklist em
`docs/owasp-web.md`. O aceite é a demonstração de fora, sem e com credencial.

## R6 · Operação

**Entregas**
- systemd timer + `OnFailure`; backup diário.
- Alerta de frescor por fonte (SIGA parado há mais de 48h, termo estável da busca PNCP com 0
  resultados, carga ARP falhando).
- Digest de novas atas de TI (`primeira_vez_vista = hoje`, em `America/Sao_Paulo`) pela bridge
  WhatsApp/WAHA existente, sem chamar Hermes/LLM (ADR 0022).
  Preservar essa data entre trocas de snapshot por chave lógica; uma recarga não transforma
  atas conhecidas em novas. Testar publicação, falha e reprocessamento.

**Critério de aceite**
- Uma semana sem intervenção manual.

**Status R6 (17/10/2026):** instalada no homelab; os três timers rodam e terminaram com
sucesso desde 15/10 (as 8 falhas da ARP foram em 14/10). O digest de 17/10 saiu em 5 mensagens
(20 atas) e o outbox não tem pendência. A semana sem intervenção conta de 15/10 e fecha em
22/10; as cargas manuais de 17/10 (R2.1 e R3) foram trabalho de entrega, não correção.
Ruído visto no digest: o termo `impressora` traz pulseira hospitalar com impressora em
comodato e filme de raio X (revisar na lista de termos da R3).

Histórico: implementação entregue neste worktree (ADR 0022), instalação e aceite
operacional pendentes. Units com `OnFailure`, operação 08:30 e backup 09:00; o backup só
publica depois de restaurar em banco temporário. Digest usa outbox, suprime carga inicial
e preserva datas entre snapshots. Gancho R3 opcional via
`contagens.resultados_por_termo` + `PNCP_TI_PNCP_TERMO`; a R3 grava o total por termo (ADR 0023), então o gancho já pode ser ligado.
Migração **0009**, seguinte à 0008; pode precisar renumeração na integração com
Claude. Testes de integração/restore real dependem de ambiente com Docker/Postgres
acessíveis; não confundir testes simulados com demonstração do critério de aceite.

## Backlog

- [x] Normalização conservadora de unidades explícitas (licença/mês, usuário/ano, página
  impressa) em `v_ata_precos_ti`, sem inferir unidade de pacotes/franquias (ADR 0022).
- Anexos e RAG (TR/ETP pelos links PNCP); retoma D3 e D4.
- [x] Servidor MCP sobre as mesmas views (stdio, SQL fixo, `mcp_reader`, SDK oficial).
- Outros sistemas estaduais com CSV próprio (BEC-SP, Compras MG...).
- Renomear o pacote `pncp_ti` e o repositório.
- [x] Manual de operação e runbook em `docs/manual-operacao.md` (antiga F7).

Anexos/RAG, outros sistemas estaduais e renomeação não foram feitos: dependem da decisão
do Lucas. O pacote continua `pncp_ti`.
