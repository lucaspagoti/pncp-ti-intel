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

**Status:** em andamento na branch `refactor/fontes-atas`.

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

**Status (16/10/2026):** implementada em `feat/r3-busca-pncp` (ADR 0023, migração 0007). Falta o
Lucas revisar `insumos/termos_ti.txt` e a avaliação de cobertura com referência independente (D6),
que não foi feita: o recall da lista de termos **não está demonstrado**.

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

## R5 · Exposição no domínio

**Entregas**
- Decisão D7. Caddy com TLS (Let's Encrypt) e autenticação na frente da web; Postgres continua em
  loopback.
- Checklist OWASP Top 10 (web).

**Critério de aceite**
- Acesso externo funciona só com credencial e recusa sem ela.

## R6 · Operação

**Entregas**
- systemd timer + `OnFailure`; backup diário.
- Alerta de frescor por fonte (SIGA parado há mais de 48h, termo estável da busca PNCP com 0
  resultados, carga ARP falhando).
- Digest de novas atas de TI (`primeira_vez_vista = hoje`, em `America/Sao_Paulo`) no Hermes.
  Preservar essa data entre trocas de snapshot por chave lógica; uma recarga não transforma
  atas conhecidas em novas. Testar publicação, falha e reprocessamento.

**Critério de aceite**
- Uma semana sem intervenção manual.

## Backlog

- Normalização de unidades de preço (licença/mês, usuário/ano, página impressa).
- Anexos e RAG (TR/ETP pelos links PNCP); retoma D3 e D4.
- Servidor MCP sobre as mesmas views (stdio, SQL fixo).
- Outros sistemas estaduais com CSV próprio (BEC-SP, Compras MG...).
- Renomear o pacote `pncp_ti` e o repositório.
- Manual de operação e runbook (antiga F7).
