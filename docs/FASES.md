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

**Entregas**
- `fontes/siga.py`: download dos 3 CSVs com timeout, limite de tamanho, sha256 e `Last-Modified`
  (pula a carga se nada mudou).
- Parse estrito: `latin1`, `;`, decimal com vírgula, datas `dd/mm/aaaa`, `trim`; cabeçalho
  diferente do esperado é falha.
- Migração `0005`: `cargas`, staging do SIGA, `atas`, `ata_itens`, `ata_participantes`, `tsvector`
  com índices GIN/trigram e views `v_atas_ti_vigentes`, `v_ata_itens_ti`, `v_ata_saldo_item`.
  Remove as tabelas da 0004, depois de `make backup` verificado.
- Classificação de TI no banco (`classificar/regra.py`). `make amostra` adaptado ao novo schema.
- Arquivo vazio, ou com menos de 50% das linhas da carga anterior, é anomalia e não publica.
- `make ingest FONTE=siga`.

**Critério de aceite**
- Duas cargas seguidas geram as mesmas contagens em `cargas`.
- `v_atas_ti_vigentes` lista as atas de TI válidas do RJ com itens e preço unitário, conferidas por
  amostragem contra o CSV.
- Link de origem: processo SEI e CSV. Verificar se o SIGA tem URL pública por ata.

## R2 · Ingestão Dados Abertos ARP

**Entregas**
- `fontes/arp.py` sobre o `DadosAbertosClient` do `compras-mcp`: atas vigentes (duas janelas de
  365 dias ou `1.2_consultarARP_FimVigencia`), filtro de TI, depois itens (`2_consultarARPItem`) só
  das atas de TI.
- Motor `ingest/executar.py` generalizado (hoje está acoplado ao `PNCPClient`). Fila
  reprocessável, com limite de taxa.

**Critério de aceite**
- Idempotência; amostra conferida contra o `linkAtaPNCP`; itens com preço unitário.

## R3 · Busca PNCP por termos de TI

**Entregas**
- `insumos/termos_ti.txt` (versionado; o Lucas revisa).
- `fontes/pncp_busca.py`: uma consulta por termo, com paginação de 500, retry e dedupe por
  `numero_controle_pncp` (o ARP tem preferência na view).
- Teste de contrato que falha alto se os campos mudarem (marcado como teste de rede).

**Critério de aceite**
- A busca de um termo conhecido bate com o portal; nenhuma duplicata com o ARP na view.

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
- Digest de novas atas de TI (`primeira_vez_vista = hoje`) no Hermes.

**Critério de aceite**
- Uma semana sem intervenção manual.

## Backlog

- Normalização de unidades de preço (licença/mês, usuário/ano, página impressa).
- Anexos e RAG (TR/ETP pelos links PNCP); retoma D3 e D4.
- Servidor MCP sobre as mesmas views (stdio, SQL fixo).
- Outros sistemas estaduais com CSV próprio (BEC-SP, Compras MG...).
- Renomear o pacote `pncp_ti` e o repositório.
- Manual de operação e runbook (antiga F7).
