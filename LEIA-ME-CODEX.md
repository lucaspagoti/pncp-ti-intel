# Leia-me — para o Codex (ou qualquer agente que continuar o trabalho)

Este arquivo é o handoff entre sessões/agentes diferentes trabalhando no mesmo projeto.
**Atualize-o sempre que parar de trabalhar**, antes de encerrar a sessão: o que foi feito, o que falta,
e qualquer decisão nova. Não deixe o próximo agente (ou o Lucas) ter que reconstruir o contexto lendo o chat.

## Seu papel: arquiteto especialista + testador, não só executor de tarefas

Você (Codex) não entra aqui só para marcar itens de uma lista. Em toda sessão neste projeto, assuma os
dois papéis abaixo, o tempo todo, sem que o Lucas precise pedir de novo:

**Arquiteto especialista.** Antes de aceitar qualquer plano, decisão ou código — seu ou de uma sessão
anterior — pergunte-se se é a escolha certa para um sistema de contratações públicas que vai informar
pesquisas pessoais de escopo nacional (ADR 0011). Isso inclui revisar criticamente o que já está feito, não só o que falta.
Se uma ADR, uma escolha de schema, uma dependência ou uma decisão de segurança te parecer frágil,
equivocada ou ultrapassada, diga isso ao Lucas explicitamente — com o porquê e uma alternativa concreta —
em vez de só seguir em frente. Proponha uma ADR nova quando for o caso.

**Testador.** Toda entrega nova (sua ou herdada) precisa ser de fato exercitada, não só lida. Rode
`make test`, suba o ambiente com `make up`, chame as tools do `compras-mcp` e do `pncp-ti` com perguntas
reais (comece pelas de `insumos/perguntas_reais.csv`), e tente ativamente achar onde quebra: dado
inesperado da API do PNCP, resposta vazia, schema mudou, ingestão duplicando, filtro de TI com falso
positivo/negativo, injeção via texto de anexo (regra fixa do `CLAUDE.md`). Não valide uma fase como
"pronta" só porque o código existe e compila — valide porque você tentou quebrar e não quebrou.

**Sempre que terminar algo:**
1. Diga explicitamente se o que foi feito (por você ou por quem veio antes) está correto, bem arquitetado
   e testado — ou não, com o motivo.
2. Liste pelo menos uma melhoria concreta que valeria a pena (mesmo que não seja para agora) — débito
   técnico, risco de segurança, oportunidade de simplificação, lacuna de teste. Registre no
   `LEIA-ME-CODEX.md` (seção "Log de sessões" ou uma seção nova "Melhorias sugeridas") para não se perder.
3. Isso não substitui o "Ciclo de cada fase" do `CLAUDE.md` — a crítica e os testes alimentam o plano que
   você propõe em modo plan; eles não são desculpa para implementar sem a aprovação do Lucas.

## Antes de fazer qualquer coisa

1. Leia nesta ordem: `CLAUDE.md` → `docs/PLANO.md` → `docs/FASES.md` → `docs/adr/` (todas) → este arquivo.
2. Respeite o "Ciclo de cada fase" do `CLAUDE.md`: proponha o plano da fase em modo plan e **espere a aprovação do Lucas**
   antes de implementar. Não pule essa etapa mesmo que pareça óbvio.
3. As regras fixas do `CLAUDE.md` (seção "Regras fixas") não são negociáveis — releia antes de tocar em
   rede, SQL, segredos ou anexos.

## Ambiente real (não é o que o pacote original presumia)

- **Não há Windows/WSL2.** Tudo roda neste servidor Linux (`homelab`), acessado via SSH. A ADR 0008
  ("local primeiro, portável para o homelab") já está satisfeita desde o início — estamos operando
  direto no que seria o destino da Fase 7. O `CLAUDE.md` já foi corrigido para Linux nativo + Docker. O `docs/PLANO.md` ainda tem
  D1/D2 como pendentes e referências ao ambiente antigo; sincronizar antes da próxima fase.
- Ferramentas confirmadas instaladas nesta máquina (12/10/2026):
  - Docker 29.5.0 + Docker Compose v5.1.3 — ok.
  - `uv` 0.13.0 — instalado em `~/.local/bin` (garanta que está no `PATH`).
  - `gh` CLI 2.102.0 — instalado via apt e **autenticado** como `lucaspagoti` (HTTPS).
  - Python do sistema é 3.14, mas o projeto usa Python 3.12 via `uv` (isolado, sem conflito).

## Decisões já resolvidas nesta sessão

- **D1 (repositório):** GitHub **privado pessoal** (não institucional). Criado e com push feito:
  https://github.com/lucaspagoti/pncp-ti-intel (branch `master`).
- **D2 (ambiente local):** servidor Linux via SSH, sem WSL2 (ver seção acima).
- **D5 (norma de pesquisa de preços):** deixou de ser bloqueante (ADR 0011) — projeto pessoal, sem
  processo formal de órgão a instruir. Nota opcional em `docs/PLANO.md`.
- D3, D4, D6 (índice vetorial, modelos locais, metas do filtro de TI) seguem **pendentes**.
- **D7 nova (ADR 0012):** mecanismo de autenticação pra exposição pública — pendente, decidir na fase
  "Exposição pública autenticada".
- **13/10/2026 — pivô de escopo (ADR 0011 e 0012):** o Lucas decidiu que o projeto não tem vínculo
  institucional nenhum (nada de PGE/GTI), escopo passa a ser **nacional** (todo o PNCP, não só RJ), e o
  destino final é hospedagem no domínio pessoal do Lucas, atrás de autenticação (só ele acessa, não é
  serviço público). A antiga Fase 1 (Reconciliação, que cruzava com uma lista de contratos da PGE) foi
  **removida** — ver `docs/FASES.md` pra numeração atual. Detalhe completo nas ADRs 0011 e 0012.

## Estado dos insumos (`insumos/`)

- `perguntas_reais.csv` — 20 linhas numeradas, mas apenas **6 perguntas preenchidas**; as linhas
  7–20 estão vazias. As 6 perguntas têm status "sugestão - revisar". Lucas ainda
  precisa revisar/confirmar antes da fase "MCP pncp-ti v1".
- `amostra_rotulada.csv` — vazio, **correto por enquanto** (é gerado pelo sistema na fase "Filtro de TI e
  preços"; não preencher antes).
- `insumos/normas/` — vazio, **opcional** (não bloqueia mais nada desde o pivô de escopo).
- `contratos_ti_pge.csv` — **removido** (13/10/2026, junto com o pivô de escopo). Nunca foi preenchido;
  sem a antiga Fase 1, não tinha mais função.

## Onde estamos no roadmap (`docs/FASES.md`)

**Fase 0 (Fundação) CONCLUÍDA, mergeada e com tag.** PR #1 mergeado em `master` em 13/10/2026
(https://github.com/lucaspagoti/pncp-ti-intel/pull/1), tag `f0-fundacao`. Critério de aceite demonstrado
ao vivo no chat com o Lucas: pergunta real ("quais atas vigentes de outsourcing de impressão existem?")
respondida via `compras-mcp` local, com fonte (ata do Batalhão da Guarda Presidencial, PNCP). O que foi
entregue:
- `pyproject.toml` (uv, Python 3.12, deps dev: pytest, pytest-asyncio, fastmcp, ruff, pre-commit).
- `tests/conftest.py` com o transporte stdio do `compras-mcp` (mesmo comando do `.mcp.json`).
- `tests/test_compras_mcp_snapshot.py` + `tests/snapshots/compras_mcp_tools.json` — snapshot de 100 tools,
  detecta "rug pull". Atualizar com `uv run python tests/test_compras_mcp_snapshot.py --update` só depois
  de ler o changelog/diff de uma nova versão do `compras-mcp` (regra do CLAUDE.md).
- `tests/test_compras_mcp_live_query.py` — chamada real a `compras_arp_buscar_por_objeto` (busca de ARPs
  vigentes por palavra-chave), cobrindo o critério de aceite "responde a uma pergunta real usando o
  compras-mcp local".
- `docker-compose.yml` — Postgres 16, porta só em `127.0.0.1:5432`, healthcheck. Testado: `make up` sobe
  saudável, `make down` derruba limpo.
- `Makefile` — `up`, `down`, `test` (lint + format-check + pytest) funcionais; `ingest`/`eval` são
  placeholders que apontam para as Fases 2/3.
- `.pre-commit-config.yaml` (ruff + gitleaks) e `.github/workflows/ci.yml` (job `test` roda `make test`;
  job `secrets-scan` roda gitleaks-action). **CI real executado no PR #1**: job `test` passou; `secrets-scan` falhou com HTTP 403
  ao ler commits do PR. Corrigido no commit `44a5c66`, concedendo apenas `contents: read` e
  `pull-requests: read` ao job de varredura. Resultado da execução corrigida: ver log abaixo.
- `make test` e `make up`/`make down` verificados localmente nesta sessão — todos passaram.

**Pendências que ficaram de fora do escopo da F0 (de propósito, ver plano aprovado):**
- `src/pncp_ti/` (ingest/classify/normalize/attachments/mcp_server) — começa na Fase 1/2.
- Alembic/schema do Postgres — Fase 2.
- `pre-commit install` não foi rodado (hooks configurados mas não instalados no `.git/hooks` local).
- `scripts/baixar_referencias.ps1` é PowerShell — não roda neste servidor Linux. Se for útil, portar para
  Python/bash numa fase futura (não bloqueia nada agora).

**Critério de aceite da Fase 0 — status:**
- ✅ `make test` verde (lint + format-check + 2 testes, incluindo chamada real ao PNCP via `compras-mcp`).
- ✅ `make up` sobe o Postgres saudável, só em `127.0.0.1:5432`, imagem pinada por digest.
- ✅ Teste de fumaça endurecido (13/10/2026): agora valida contrato estrutural (campos esperados em
  cada item), que `dataVigenciaFinal` respeita a janela pedida e que `objeto` de fato contém a
  palavra-chave — não só que a tool rodou. Documenta explicitamente que distinguir outsourcing real de
  falso positivo (papel, plotagem) é trabalho do classificador da Fase 3, não deste teste.
- ✅ Demonstração ao vivo no chat em 13/10/2026: pergunta "quais atas vigentes de outsourcing de
  impressão existem?" respondida chamando `compras_arp_buscar_por_objeto` de verdade. Resultado: ata
  90003/2025 do Batalhão da Guarda Presidencial (Comando do Exército), vigência até 14/10/2026, fonte
  https://pncp.gov.br/app/atas/00394452000103/2025/18457/1. Um 2º match ("outsourcing" de materiais de
  manutenção predial, IFCE) foi corretamente descartado por não ser sobre impressão — julgamento que a
  Fase 3 (classificador) vai automatizar, mas que por ora cabe a quem está respondendo (humano ou agente).

**Lacunas da revisão do Codex, fechadas em 13/10/2026 (mesma branch, antes do merge):**
1. Teste de fumaça fortalecido (ver acima).
2. `docs/PLANO.md` sincronizado: D1 e D2 marcados como resolvidos.
3. `compras-mcp` agora é dependência declarada em `pyproject.toml` (`==0.4.0`), travada no `uv.lock` com
   hashes — protege a árvore transitiva inteira, não só o pacote top-level (ADR 0002). `.mcp.json` e
   `tests/conftest.py` trocaram de `uvx --from ...` para `uv run --project . compras-mcp`, usando o
   ambiente travado. Testado: `uv sync`, `make test` e `make up` continuam verdes.
4. Postgres pinado por digest em `docker-compose.yml`
   (`postgres@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d`, = `postgres:16`
   em 12/10/2026). Atualizar o comentário junto do digest quando trocar de versão.
5. Job `vuln-scan` novo em `.github/workflows/ci.yml` (Trivy): varre `uv.lock` (filesystem) e a imagem do
   Postgres, falha em CRITICAL/HIGH com correção disponível. **Já achou vulnerabilidades reais na
   primeira execução** (exatamente a função dele): CVE-2026-32871 (CRITICAL) e CVE-2026-27124 (HIGH) no
   `fastmcp` 2.14.7 (transitivo do `compras-mcp`, que trava `fastmcp<3.0` — upstream ainda não suporta
   3.x), e 25 CVEs + 1 falso positivo de segredo na imagem oficial `postgres:16` (binário `gosu`
   vendorizado + chave placeholder Debian). Investiguei cada um (código-fonte do `compras-mcp`, natureza
   do `gosu`), confirmei que os caminhos vulneráveis são inatingíveis na nossa implantação, e suprimi via
   `.trivyignore` com justificativa — ver **ADR 0010** para o raciocínio completo e os gatilhos pra
   revisitar. Scan validado localmente (`trivy` instalado em `~/.local/bin`) antes de confiar no CI.

**Status: fase fechada.** PR #1 mergeado em `master` (`e895b27`), tag `f0-fundacao`. Branch
`feat/f0-fundacao` deletada (já está em `master`).

**Próximo passo (superado — ver Fase 1 abaixo):** propor o plano da Fase 1 em modo plan.

**Atualização após a revisão (12/10/2026):** os achados foram corrigidos com autorização de Lucas,
com migração 0002 e ADR 0013. As descrições de checkpoint e restauração da implementação original
abaixo são históricas e foram substituídas pela última entrada do log de sessões. A F1 continua
em andamento porque o backfill completo/CI remoto ainda estão pendentes.

**Fase 1 (Base histórica) — EM ANDAMENTO**, branch `feat/f1-base-historica`, plano aprovado pelo Lucas
em 12/10/2026 (duas decisões de escopo confirmadas por `AskUserQuestion` antes de implementar: itens de
contratação/preço por unidade ficam fora da F1 — só entram na Fase 2, e só para contratações marcadas TI
pelo classificador; backfill retroativo até 01/04/2023, início da obrigatoriedade do PNCP). Entregue
nesta sessão:
- `db/migrations/versions/0001_f1_base_historica.py` (Alembic) — tabelas `orgaos`, `fornecedores`, `contratacoes`,
  `atas`, `contratos` (cada uma com coluna `raw jsonb` guardando o payload inteiro — protege contra campo
  novo/renomeado no PNCP sem quebrar a ingestão) e `log_execucao_ingestao` (ADR 0005). Papéis `ingest`
  (INSERT/UPDATE/SELECT nas tabelas base) e `mcp_reader` (SELECT só em `v_contratacoes`/`v_atas`/
  `v_contratos`, sem acesso a `raw`) — testado manualmente que `mcp_reader` não lê nem escreve tabela
  base. `make migrate` novo no Makefile.
- `src/pncp_ti/` — pacote novo (`pyproject.toml` deixou de usar `bypass-selection`). `config.py` (lê
  `.env`), `db.py` (upsert genérico por chave natural), `mask.py` (CPF mascarado — regra fixa do
  CLAUDE.md), `ingest/` com `windows.py`, `rate_limit.py`, `client.py` (reusa
  `compras_mcp.clients.pncp.PNCPClient`, ADR 0004 — nenhum cliente HTTP novo), `mapeadores.py`,
  `executar.py` (núcleo paginação+upsert+log, compartilhado pelos 3 adaptadores), `contratacoes.py`,
  `atas.py`, `contratos.py`, `log.py`, `cli.py` (`--diario` e `--backfill`).
- **Dois achados reais por chamada direta à API do PNCP (não documentados no `compras-mcp`), que mudaram
  o desenho da ingestão:**
  1. O limite real de janela é **365 dias** para `/v1/contratacoes/publicacao`, `/v1/atas` e
     `/v1/contratos` — o comentário do `compras-mcp` cita "~30 dias" para contratações, mas testei
     diretamente e o próprio PNCP aceita até 365 (422 só acima disso). `windows.py` usa 365 para as três.
  2. `/v1/atas` filtra por **sobreposição de vigência**, não por data de publicação — uma ata com
     vigência de anos aparece em toda janela que a sobrepõe (confirmado: uma janela de 1 dia já trouxe
     ~490 mil atas nacionalmente). Inofensivo pro upsert (idempotente), só caro em chamadas; documentado
     em `atas.py`.
  3. **Quirk de robustez real, corrigido:** quando uma combinação (modalidade/entidade/janela) não tem
     nenhum resultado, o PNCP responde **204 com corpo vazio** em vez de `200 {data: []}` — o
     `BaseAsyncClient` do `compras-mcp` tenta decodificar JSON vazio e levanta `ComprasHTTPError`. Sem
     tratar isso, a ingestão diária quebraria toda vez que uma modalidade não tivesse nada no dia (a
     maioria dos dias, pra a maioria das 13 modalidades). `executar.py` (`_buscar_pagina`) trata esse
     caso como página vazia real, e separadamente faz retry com backoff (até 6 tentativas, 15s→180s)
     pra `ComprasRateLimitError`/`ComprasServerError`/`ComprasTimeoutError` — descobri na prática que o
     backfill real bate em 429 sustentado numa modalidade concorrida (Pregão Eletrônico) mesmo com
     limitador de 2 req/s, e os 2 retries internos do cliente não bastam pra um job de horas. Os dois
     comportamentos têm teste (`tests/test_ingest_upsert.py`), incluindo um client PNCP falso simulando
     o 204.
- **Testes** (`make test` verde, 11 testes): `test_ingest_windows.py` (geração de janela, sem rede/banco);
  `test_ingest_upsert.py` (idempotência real — mesma janela processada duas vezes via um client PNCP
  falso → mesma contagem em `contratacoes`, critério de aceite da fase; mais o teste do quirk 204) contra
  um Postgres de teste dedicado (`pncp_ti_test`, criado e migrado por fixture de sessão em
  `tests/conftest.py`, nunca o banco de desenvolvimento); `test_ingest_live_smoke.py` (rede real, 1
  chamada pequena por entidade — contratações, atas, contratos — grava no banco de teste, detecta campo
  renomeado na API antes de confiar num backfill de horas).
- **CI** (`.github/workflows/ci.yml`): job `test` ganhou um serviço Postgres (mesmo digest pinado do
  `docker-compose.yml`) e um passo `make migrate` antes de `make test` — as credenciais no YAML são só do
  Postgres efêmero do job (descartado ao fim), não segredos reais.
- `scripts/backup_postgres.sh` (`pg_dump` custom format) + `make backup`; passo de restauração
  documentado no `README.md` (não automatizado em CI — é operacional, não testável sem destruir o volume
  local).
- `README.md` e `CLAUDE.md` atualizados (comandos novos, status, nota de que itens ficam pra Fase 2).
  Corrigi também a referência obsoleta no `README.md` à extinta "Fase 1 (Reconciliação)".
- Validado localmente: `make up`, `make migrate`, `make test` (11/11), e uma chamada real da CLI
  (`--backfill --desde <2 dias atrás> --entidades contratacoes`) até bater no 429 sustentado acima — foi
  esse teste que revelou o achado 3. Depois de corrigir, **não tornei a rodar um backfill completo**: o
  banco de desenvolvimento foi limpo (`TRUNCATE`) de volta a vazio de propósito, pra o Lucas decidir
  quando/como rodar o backfill real (`make ingest-backfill`, horas de duração — ver README).

**Pendências que ficaram de propósito fora do escopo desta sessão:**
- Não rodei o backfill completo (2023-04-01 até hoje) — é um job de horas; decisão de quando rodar é do
  Lucas. `log_execucao_ingestao` garante que pode ser interrompido e retomado sem reprocessar.
- Não testei restauração de backup de verdade (passo documentado, mas exige destruir e recriar o volume
  Docker local — não fiz sem o Lucas presente).
- Ainda não abri PR nem mergeei — branch `feat/f1-base-historica` local, aguardando revisão.

**Revisão independente feita nesta sessão** (8 ângulos via subagentes — correção, comportamento removido,
cross-file, reuso, simplificação, eficiência, altitude, convenções do CLAUDE.md). Achados reais,
corrigidos no mesmo branch (commit separado, não amend):
- Página com item com falha ficava marcada `ok` no log (nunca mais seria reprocessada) — agora só fica
  `ok` sem nenhuma falha de item.
- `--forcar` quebrava com `UniqueViolation` ao reprocessar janela já `ok` — `registrar()` agora usa
  `ON CONFLICT` contra o índice único parcial em vez de `INSERT` puro.
- Falha num item "envenenava" a conexão (sem savepoint) e derrubava os itens seguintes da mesma página
  em cascata — cada item agora roda sob savepoint (`conn.transaction()` aninhado).
- Detecção do quirk 204 do PNCP batia em qualquer JSON malformado, não só corpo vazio de verdade —
  tratamento restrito ao corpo genuinamente vazio.
- `raw jsonb` de contrato guardava CPF sem máscara mesmo com a coluna estruturada mascarada; `mascarar_ni`
  tinha uma condição morta que deixava passar CPF com menos de 11 dígitos sem máscara — os dois
  corrigidos (regra fixa do CLAUDE.md, "CPFs sempre mascarados").
- `get_settings()` exigia as três senhas de uma vez; `alembic downgrade`/`make ingest` não usam todas —
  validação movida pro ponto de uso.
- `db.upsert()` geraria SQL inválido num caso hoje inexistente (só coluna-chave) — guarda defensiva.

Testes novos por bug corrigido. `make test` 18/18 verde; migração testada do zero de novo depois da
mudança em `config.py`. Achados de menor severidade (não corrigidos, documentados como decisão): papéis
de banco criados em duas etapas (SELECT + CREATE ROLE) em vez de um bloco `DO` atômico — risco só sob
migração concorrente, improvável neste projeto pessoal de operador único; parâmetro `tabela` de
`ingerir_janela` duplica `entidade` nos três adaptadores atuais, mas são conceitos intencionalmente
desacoplados (o próprio teste de idempotência usa `entidade` diferente de `tabela` para isolar dados de
teste) — não é uma falha latente, decidi não unificar.

**Próximo passo:** demonstrar o critério de aceite com o Lucas, decidir quando rodar
`make ingest-backfill` de verdade (job de horas), abrir PR, e só então Fase 2.

## Convenções do projeto

- Documentação e mensagens: português (Brasil). Código, nomes de variáveis e commits: inglês.
- Commits seguem conventional commits (ex: `chore:`, `feat:`, `fix:`) — ver `git log`.
- Toda decisão nova vira ADR em `docs/adr/`, numerada sequencialmente (próxima: `0014-...`; 0013 criada nesta correção).
- Nenhum segredo no repositório; `.env` é local e já está no `.gitignore`.

## Log de sessões

- **2026-10-12 (Claude/Sonnet 5, sessão inicial):** pacote descompactado, git inicializado e commitado
  (`5d1dd15`). Identidade git configurada (lucas / lucaspagoti95@gmail.com). Li todos os documentos do
  pacote. Resolvi D1 (GitHub privado pessoal) e D2 (Linux via SSH, sem WSL2) com o Lucas. Instalei `uv`
  e `gh` CLI, autentiquei `gh` como `lucaspagoti`. Criei repo privado
  https://github.com/lucaspagoti/pncp-ti-intel e dei push do commit inicial. Corrigi a referência a
  Windows/WSL2 no `CLAUDE.md` (agora: servidor Linux via SSH). Criei este arquivo.
  **Próximo passo:** propor o plano da Fase 0 em modo plan para aprovação do Lucas, depois implementar.
- **2026-10-12 (Claude/Sonnet 5, mesma sessão, Fase 0):** plano da Fase 0 aprovado pelo Lucas. Implementei
  em `feat/f0-fundacao`: tooling (`pyproject.toml`, `Makefile`, `docker-compose.yml`, pre-commit, CI),
  testes reais contra o `compras-mcp` (snapshot de 100 tools + chamada de fumaça), tudo verificado
  localmente (`make test`, `make up`/`make down`). Atualizei `README.md` e `CLAUDE.md`. Ver seção
  "Onde estamos no roadmap" acima para o detalhe completo e as pendências deixadas de propósito fora do
  escopo. **Próximo passo:** abrir PR, revisar, mergear, e depois a Fase 1.

- **2026-10-12 (Codex, revisão da F0):** li CLAUDE.md, PLANO.md, FASES.md e todas as ADRs.
  Preservei as alterações de handoff que já estavam no arquivo. Localizei PR #1 já aberto e
  anexei ao chat; fiz revisão independente por subagente (segurança e aceite). `make test` passou
  (lint, formato e 2 testes); primeiras tentativas falharam por permissões do sandbox nos caches
  do uv/uvx, não por falha da API. `.env` estava ausente: criei arquivo local com senha aleatória
  e modo 0600, sem versionar nem exibir o segredo. `make up` subiu Postgres saudável; `docker inspect`
  confirmou bind 127.0.0.1:5432; `make down` passou, preservando volume. Não há servidor `pncp-ti`
  implementado para exercitar ainda. Corrigi HTTP 403 do job secrets-scan no commit `44a5c66`,
  revisado pelo subagente e enviado ao PR.
  **Avaliação:** estratégia de composição, stdio e bind local são adequados; fundação testada,
  mas F0 ainda não plenamente aceita. Não fiz merge/tag nem iniciei F1.
  **Melhorias concretas:** (1) distinguir fumaça de resposta funcional, testar contrato do payload
  e demonstrar outsourcing com links e ressalvas de adesão/varredura parcial; (2) fixar compras-mcp
  e transitivas por lock/hashes — `uvx --from compras-mcp==0.4.0` está fora do uv.lock e snapshot
  de metadados não protege contra mudança de código; (3) fixar Postgres por digest; (4) incluir
  varredura de vulnerabilidades prevista no plano; (5) sincronizar D1/D2 e contagem de perguntas.
  **Demonstração:** candidatos retornados: Batalhão de Guarda Presidencial, ata 90003/2025
  (fim 14/10/2026, https://pncp.gov.br/app/atas/00394452000103/2025/18457/1); Câmara Municipal
  de Macapá, ata 00004/2024 (fim 15/10/2026, https://pncp.gov.br/app/atas/04188116000157/2024/2/1);
  SEFAZ/GDF, ata 00250/2024 (fim 16/10/2026, https://pncp.gov.br/app/atas/00394684000153/2024/730/1).
  A resposta da busca não comprova autorização/saldo para adesão estadual.
  **CI após correção:** jobs `test` e `secrets-scan` verdes na execução 38302340655
  (https://github.com/lucaspagoti/pncp-ti-intel/actions/runs/38302340655).
- **2026-10-13 (Claude/Sonnet 5, fechando as lacunas da revisão do Codex):** revisei os apontamentos
  (commits `44a5c66` e `f0bfd26`) um por um, confirmei que `perguntas_reais.csv` tem mesmo só 6 linhas
  preenchidas (`awk` confere). Concordei com as 5 lacunas e fechei todas na mesma branch
  `feat/f0-fundacao`: teste de fumaça agora valida contrato estrutural e janela de vigência, não só que a
  tool rodou; `docs/PLANO.md` sincronizado (D1/D2 marcados); `compras-mcp` virou dependência travada no
  `uv.lock` com hashes, `.mcp.json`/testes trocaram `uvx --from` por `uv run --project . compras-mcp`;
  Postgres pinado por digest; job `vuln-scan` (Trivy) novo no CI. `make test` e `make up`/`down`
  verificados localmente de novo após cada mudança — todos verdes. Empurrei e acompanhei o CI real: job
  `vuln-scan` achou 2 CVEs reais no `fastmcp` (transitivo do `compras-mcp`) e 25 + 1 falso positivo na
  imagem oficial do Postgres. Investiguei a fundo (baixei e inspecionei o código-fonte do `compras-mcp`,
  confirmei que as features vulneráveis do FastMCP — OpenAPI proxy, OAuthProxy — não são usadas), escrevi
  a **ADR 0010** e um `.trivyignore` com justificativa específica e gatilho de revisão para cada
  supressão — não desliguei nem afrouxei o scanner. Instalei o `trivy` local (`~/.local/bin`) pra validar
  antes de confiar no CI. **Próximo passo:** empurrar esta rodada, conferir os 3 jobs de CI verdes de
  novo, demonstrar o critério de aceite com o Lucas no chat, então merge/tag e Fase 1.
- **2026-10-13 (Claude/Sonnet 5, fechamento da Fase 0):** CI real confirmado verde nos 3 jobs
  (`test`, `vuln-scan`, `secrets-scan`) após a rodada de supressões justificadas. Demonstração ao vivo no
  chat com o Lucas: pergunta real sobre outsourcing de impressão respondida com fonte via `compras-mcp`
  (detalhe acima, seção "Onde estamos no roadmap"). Lucas aprovou. Mergeei PR #1 em `master` (`e895b27`,
  fast-forward/squash pela interface do `gh`), criei e empurrei a tag `f0-fundacao`, deletei a branch
  `feat/f0-fundacao`. **Fase 0 oficialmente encerrada.** Próxima ação registrada então: propor o plano
  da Fase 1 (Reconciliação) — **superada pelo pivô abaixo, no mesmo dia.**
- **2026-10-13 (Claude/Sonnet 5, pivô de escopo):** o Lucas pediu, antes de eu propor o plano da Fase 1,
  pra remover todo vínculo institucional do projeto (nada de PGE/GTI), remover a fase de Reconciliação
  por completo, e definir o destino final como hospedagem no domínio pessoal dele, atrás de autenticação
  (só ele acessa). Esclareci com perguntas: escopo geográfico vira **nacional** (todo o PNCP, não só
  RJ); critério de "o que é TI" continua curadoria pessoal dele. Documentei em modo plan, aprovado, e
  executei: `CLAUDE.md`, `README.md`, `docs/PLANO.md`, `docs/FASES.md` (removida a F1, fases renumeradas
  F1–F7), `docs/GLOSSARIO.md`, `docs/referencias/LINKS.md`, `insumos/LEIA-ME.md`,
  `insumos/normas/LEIA-ME.md`, `Makefile`, `pyproject.toml` generalizados; `insumos/contratos_ti_pge.csv`
  removido (nunca foi preenchido); ADR 0001 e 0006 com contexto generalizado (decisão em si não mudou);
  ADR 0011 (escopo nacional, sem vínculo institucional) e ADR 0012 (exposição pública autenticada —
  mecanismo fica como decisão D7, não travado agora) criadas. Validei com
  `grep -ril "pge\|gti\|siga-rj"` que não sobrou menção fora deste log e da própria ADR 0011 (que cita a
  PGE como contexto histórico da mudança, de propósito). **Próximo passo:** propor o plano da **Fase 1
  (Base histórica)** em modo plan — sem bloqueio de insumo, pode começar assim que aprovado.


## Revisão geral do Codex — 12/10/2026, HEAD e08caee

**Conclusão: F1 ainda não aprovada para merge/backfill completo.** Revisados os três commits
4347c41, 55a0d0c e e08caee; revisão independente adicional por subagente de segurança.
Arquitetura de composição, cliente reusado, views e savepoints são adequados, mas há bugs
confirmados não cobertos pelos 18 testes. Nenhum código de produção foi alterado nesta revisão.

**Validação:** `make up` saudável e bind 127.0.0.1; `make migrate` passou; `make test` passou
18/18 (incluindo snapshot e consultas reais às três entidades). Bancos novos descartáveis foram
migrados e usados para reproduções; removidos ao final. `make backup` falhou: `pg_dump: command
not found` no host. Alternativa testada com pg_dump do container: backup restaurado em banco limpo
no mesmo cluster, com contagens de seis tabelas iguais e três views presentes; leitura de view
permitida ao mcp_reader e tabela base negada. Restaurar em schema já existente falha (`already
exists`), portanto corrigir receita do README que manda migrar antes do restore. Teste de restore
não exige destruir volume local. Papéis globais já existiam: falta ensaio em cluster novo.
Postgres já estava rodando antes da revisão e permaneceu rodando; banco/volume de desenvolvimento
preservados. Sem backfill completo, push, PR, merge ou tag.

**Achados a resolver:**
- P1: `_raw_sem_cpf` mascara só niFornecedor. Schema oficial RecuperarContratoDTO também tem
  niFornecedorSubContratado/tipoPessoaSubContratada; CPF sintético PF desse campo ficou intacto
  no raw. Corrigir antes de ingerir dados em volume.
- P1: CPF mascarado usado como PK/FK funde fornecedores distintos; dois CPFs sintéticos válidos
  produzem a mesma máscara. Separar identidade interna da máscara de apresentação (avaliar HMAC
  com segredo local em ADR; não armazenar CPF original nem inferir identidade só de máscara upstream).
- P1: checkpoint por página/janela marcado ok pula atualizações. Reprodução: segunda execução
  após mudança de objeto só pediu página 2 e preservou dado antigo. Fonte/paginação mutável não
  tem retomada segura apenas por offset; separar retomada de nova sincronização. A rotina diária
  também precisa capturar atualizações de publicações antigas.
- P1: log.exception usa traceback Rich com variáveis locais; reprodução com o mesmo logger
  expôs CPF sintético do payload. Desativar locais e sanitizar mensagens/contextos de erro.
- P2: envelope sem data/totalPaginas vira página vazia ok; schema alterado reproduzido no banco.
  Validar contrato antes de gravar checkpoint, sem valores padrão que escondam schema inválido.
- P2: erro de item fica no log mas a função/CLI conclui sem sinalizar falha ao job. Preservar itens
  bons e savepoints, porém agregar falhas e retornar código não zero quando houver perda.
- P2: backup depende de cliente ausente no host; receita de restore conflita com tabelas pré-criadas.
  Usar cliente do container ou provisionar versão compatível e restaurar em banco limpo com fail-fast.
- P2: extrair_orgao_de_ata + upsert apaga poder_id/esfera_id conhecidos com NULL (reproduzido).
- P2: DSNs interpolam senha sem encoding; caracteres @/% quebram host/decoding/Alembic. Construir
  conexão de forma estruturada e cobrir caracteres especiais também nas fixtures.

**Melhorias/documentação:** adicionar regressões para os casos acima, atualizar ADR 0004 sobre
cliente já escolhido, conciliar itens adiados com FASES.md e medir custo da carga diária de atas.
Próxima ADR livre é 0013 (não 0010). A documentação ainda contém fases antigas, referência à GTI
no papel de arquiteto e datas de 13/10/2026 em entradas anteriores apesar do contexto desta revisão
ser 12/10/2026; preservar histórico até confirmar as datas. Caminho real da migração tem versions/.

Relatório detalhado desta revisão salvo em:
/home/lucas/Documents/Codex/2026-10-12/em-home-lucas-projetos-pncp-ti-5/outputs/revisao-f1.md

**Próximo passo:** corrigir achados e acrescentar testes de regressão na F1; revisar novamente,
validar CI quando houver PR e então demonstrar critérios de aceite/backfill combinado com Lucas.


## Correções autorizadas pelo Lucas — 12/10/2026

A instrução “pode consertar” autorizou fechar os achados desta revisão na mesma branch.
Implementação e testes revistos novamente por subagente independente; nenhum bloqueador restante
na revisão final. Alterações ficaram locais, sem push/PR/merge/tag.

- Identidade de fornecedor separada da máscara: fornecedores.fornecedor_id PK, contratos.fornecedor_id
  FK; HMAC-SHA256 para CPF e escopo por contrato para documento incompleto/mascarado na origem.
  PNCP_TI_IDENTITY_KEY forte gerada no .env local, nunca versionada/exibida. Backup cifrado da
  configuração deve preservar essa chave; rotação exige plano de migração/reingestão (ADR 0013).
- Migração 0002 aplicada ao desenvolvimento sem apagar dados: preserva PJ, limpa CPF de JSON/textos
  legados e deixa vínculo PF ambíguo NULL até reingestão. Máscara não permite reconstruir identidade.
  Testes também exercitam upgrade de banco legado com dados sintéticos; downgrade recusa colisões.
- CPF do subcontratado, campos novos de CPF e CPFs em texto mascarados em raw/colunas textuais.
  Preços numéricos preservados. Logs de erro só contêm classe e contexto fixo, sem payload/traceback.
- Toda nova execução reprocessa páginas e faz upsert de verdade. Sem checkpoint por offset de fonte
  mutável; --forcar mantido por compatibilidade. Diário lê também atualizações de contratações antigas.
  Envelope/paginação incoerentes geram erro, nunca sucesso vazio. Itens bons preservados por savepoint;
  falhas agregadas fazem CLI retornar 1. Metadados conhecidos de órgãos não são apagados por NULL.
- DSNs/URLs estruturados aceitam caracteres especiais; Alembic não usa interpolação de ConfigParser.
  Criação de papéis também trata % corretamente. Fixtures usam bancos UUID e identificadores SQL
  escapados, sem apagar bancos existentes. Testes não compartilham o banco de desenvolvimento.
- make backup usa pg_dump do container, arquivo 0600/publicação atômica e diretório 0700; sem source
  do .env. make restore exige destino novo, provisiona papéis em banco descartável separado e usa
  pg_restore --exit-on-error --single-transaction. Recusa destino atual/existente/sistema.
- README, FASES.md, ADR 0004 e ADR 0013 sincronizados; próximo número ADR livre: 0014.

**Validação operacional:** make migrate passou; backup real novo gravado localmente e validado.
Restauração exercitada em CLUSTER DOCKER NOVO (tmpfs, porta só em 127.0.0.1), com senhas sintéticas
contendo @/%/:/?/#/$/&/aspas/barra/espaço: papéis provisionados, dump com dois fornecedores PF com
mesma máscara restaurado com dois IDs distintos, FK e versão 0002 conferidas; login ingest testado,
view permitida e tabela base negada ao reader. Segundo restore no mesmo destino foi recusado.
Bancos/dump/container de validação removidos; banco/volume de desenvolvimento preservados.
Cron de backup foi documentado, não ativado. Nenhum backfill completo iniciado.

**Avaliação:** correções arquitetadas e testadas com regressões e operação real; critérios parciais
de idempotência e recuperação demonstrados. A F1 inteira só estará pronta após backfill combinado,
CI remoto e demonstração final com Lucas. Melhoria concreta futura: reconciliar periodicamente
janelas e medir chamadas/duração da carga diária de atas; paginação upstream não oferece snapshot
transacional. Logs por execução com identificador próprio melhorariam auditoria de reexecuções.

**Verificação final:** make test verde (lint, formato e **54/54 testes**, incluindo consulta real de
atualizações PNCP), bash -n verde, git diff --check verde. Duas depreciações de dependências herdadas.

**Commit de correções:** 04dd623 (fix: protect supplier identity and harden historical ingestion).
Documentação/handoff registrados em commit local separado. Branch não enviada ao GitHub.
