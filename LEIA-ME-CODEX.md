# Leia-me — para o Codex (ou qualquer agente que continuar o trabalho)

Este arquivo é o handoff entre sessões/agentes diferentes trabalhando no mesmo projeto.
**Atualize-o sempre que parar de trabalhar**, antes de encerrar a sessão: o que foi feito, o que falta,
e qualquer decisão nova. Não deixe o próximo agente (ou o Lucas) ter que reconstruir o contexto lendo o chat.

## Estado vigente: R1 (SIGA RJ) implementada, aceite pendente — 13/10/2026 (Claude/Sonnet 5.5)

**Este bloco substitui os abaixo.** R0 foi mergeada (PR #4). Branch da R1: `feat/r1-siga-rj`.
Leia a ADR 0019 e `docs/FASES.md` (R1).

- **Feito:** migração `0005`; `fontes/siga.py` + `fontes/siga_csv.py` (download, validação, carga
  atômica); `classificar/in05.py` (regra pelo Anexo Único da IN PRODERJ/PRE 05/2024, PDF em
  `insumos/normas/`); `classificar/amostra.py` (censo) e `classificar/avaliar.py`; testes
  (`make test`: 156). Migração aplicada ao banco local **depois** de backup restaurado em banco
  temporário (removido). Carga real feita duas vezes (a segunda, `sem_mudanca`).
- **Descobertas que mudaram o desenho** (detalhe na ADR 0019): `ID Ata` repete por processo SEI;
  linhas idênticas em itens/participantes; arquivos são **cp1252**, não latin-1; CPF no nome de
  fornecedor; consumo > demanda em 4.155 linhas (por isso `v_ata_consumo_item`, não "saldo").
- **Decidido pelo Lucas (13/10/2026):** seguir o Anexo Único da IN 05, inclusive telefonia/voz/
  internet, pontos de rede lógicos e videomonitoramento/CFTV (a resposta anterior excluía isso).
  Nobreak e drone continuam fora (não constam do anexo). Resultado: 25 atas de TI vigentes.
- **Pendente:** (1) rotular `insumos/rotulagem_siga.csv` (1.574 atas; não versionado ainda);
  (2) `make eval ROT=...` e ajuste da regra até a meta D6 (proposta: recall ≥ 95%, precisão ≥ 85%);
  (3) reclassificar com `make ingest ARGS=--forcar` depois de mudar a regra.
- **Não fazer:** mudar `CATEGORIAS_FORA_DE_ESCOPO` sem o Lucas; afirmar recall antes da rotulagem;
  estender o critério do anexo (norma do RJ) às fontes federal/municipal sem decisão.
- **Próximo:** fechar a R1 (rótulos + eval + conferência de 10 atas), depois R2 (ARP). A R2 precisa
  generalizar `ingest/executar.py`, ainda acoplado ao `PNCPClient`, e que grava por página.

## Continuação vigente — ajustes da revisão R0, Codex, 13/10/2026

Lucas autorizou os ajustes da revisão e o registro para o Claude continuar. Este bloco
complementa o estado R0 abaixo; os registros F2/F3 anteriores permanecem históricos.
Branch: `refactor/fontes-atas`; base revisada: `042c21b`.

**Feito nesta sessão:**
- ADR 0004 atualizada para distinguir o wrapper PNCP removido (histórico) do reuso de
  `DadosAbertosClient` previsto na R2 e dos clientes finos autorizados na ADR 0016.
- ADR 0016 e PLANO deixam a sobreposição SIGA/PNCP a confirmar: a busca notebook/RJ
  não demonstra ausência universal. Sem fusão automática por semelhança de objeto.
- A duração da carga é estimativa a medir nos pilotos, incluindo itens ARP e retries.
- FASES explicita idempotência com os mesmos três CSVs e a mesma data de referência,
  teste do caminho sha256 inalterado, avaliação de cobertura com referências fora dos
  resultados da lista de termos e preservação de `primeira_vez_vista` entre snapshots.
- `make ingest` agora retorna erro enquanto for placeholder, evitando falso sucesso
  para futuros agendadores. CLAUDE e README acompanham esse comportamento.

**Validação:** `PYTEST_ADDOPTS='--tb=no' make test` passou: lint e formatação verdes,
79 testes aprovados em 10,00 s, incluindo as duas migrações em bancos temporários.
`--tb=no` apenas suprime tracebacks; não omite testes. `git diff --check` passou.
`make ingest` foi exercitado e recusou executar, com retorno não zero esperado.
A revisão inicial teve 77 aprovados e duas falhas de conexão ao Postgres; o ambiente
subsequente sem sandbox permitiu concluir a suíte. A tentativa intermediária de conceder
escrita a um arquivo individual produziu erro de montagem bubblewrap (arquivo tratado
como diretório). Não houve alteração de configuração global do Codex: a correção prática
foi a atualização das permissões pelo ambiente desta conversa. Em futuras sessões,
conceder acesso à pasta do projeto, evitando esse alvo de arquivo individual.

Revisão independente do diff pelo subagente concluída: ajustes aprovados, sem novo
achado bloqueante.

**Parecer:** ajustes resolvem os achados da revisão; R0 tecnicamente validada localmente.
Aprovação do Lucas, CI remoto, PR/merge e tag permanecem separados. Não afirmar que R1,
novas fontes, web ou operação estão implementadas. Os testes não demonstram cobertura
nacional, ausência de sobreposição SIGA/PNCP ou tempo real das futuras cargas.

**Para o Claude continuar:** revisar o diff não commitado e fechar R0 conforme o fluxo
aprovado pelo Lucas; depois propor o plano R1 antes de codar. Na R1, validar consistência
do conjunto dos três CSVs, preservar chaves para futuras fontes e conferir backup por
restauração antes da migração 0005. Na R2, medir custo total atas + itens. Na R3, definir
com Lucas D6 e a amostra de cobertura externa à busca. Na R6, testar que recargas não
reenviam atas conhecidas como novas.

Melhoria adicional para o plano R1: detectar arquivos de gerações diferentes entre os
três downloads, sem publicar um conjunto incoerente. O motor ainda grava por página;
qualquer reuso deve escrever em staging e publicar somente após concluir a fonte.
Nenhuma ingestão real, migração do banco principal, alteração de serviços, commit,
push, PR ou merge foi feita nesta sessão.

## Estado vigente: mudança de arquitetura (R0), 13/10/2026 (Claude/Opus 5.5)

**Este bloco substitui tudo o que vem abaixo** sobre F2, F3, MCP e snapshot `/v1/atas`. Leia as ADRs
0016, 0017 e 0018, `docs/PLANO.md` e `docs/FASES.md`.

- **Fontes (ADR 0016):** SIGA RJ (3 CSVs diários), Dados Abertos Compras.gov.br `modulo-arp` (500
  por página) e a busca do portal PNCP (`/api/search`, por termos de TI). O snapshot PNCP `/v1/atas`
  foi abandonado; **não o repita**. O Portal da Transparência da CGU está fora (não tem atas;
  "Licitações" parou em 2024).
- **Orquestração (ADR 0017):** systemd timer + `make ingest`. O Airflow fica adiado.
- **Interface (ADR 0018):** web própria FastAPI + Jinja2 + HTMX, papel `web_reader`. Exposição no
  domínio só atrás de proxy TLS + autenticação (D7). O MCP saiu do caminho crítico: `.mcp.json` e
  os testes do servidor `compras-mcp` foram removidos. O pacote `compras-mcp==0.4.0` continua como
  biblioteca (`DadosAbertosClient`).
- **R0 na branch `refactor/fontes-atas`** (criada a partir de `feat/f2b-itens-atas`, para manter o
  retry `a1fc870`). Foram removidos `ingest/atas.py`, `cli.py`, `mapeadores.py`, `client.py` e os
  testes correspondentes. Ficaram `ingest/executar.py`, `windows.py`, `log.py` e `rate_limit.py`,
  que serão generalizados na R2. `classificar/amostra.py` ainda lê as tabelas da 0004 e é adaptado
  na R1.
- **Banco local:** migração 0004 aplicada, sem atas carregadas. A R1 traz a migração 0005, que
  substitui essas tabelas (com `make backup` verificado antes).
- **Próximo passo:** o Lucas aprova a R0 (PR) → plano da R1 (SIGA RJ) em modo plan.

## Estado anterior: F2A mergeada; preparação da Fase 3 (13/10/2026, histórico)

**Escopo: somente atas de TI vigentes; backfill histórico cancelado (ADR 0015).** Os registros
abaixo desta seção são histórico de sessões e podem conter instruções já superadas.

A F1 foi mergeada no PR #2. A F2A foi mergeada no [PR #3](https://github.com/lucaspagoti/pncp-ti-intel/pull/3)
em 13/10/2026 (merge commit `df301c3`; head `dfda755` inclui retenção de 30 dias dos logs por página).
O CI do head passou. A branch local de trabalho é `feat/f2b-itens-atas`, criada sobre `master` já
atualizado (`df301c3`); há commits locais de documentação (`9dcc596`) e de retry HTTP (`a1fc870`), sem
push ou PR desta etapa.

O desenho foi aprovado após corrigir: publicação indevida de carga parcial após 204 intermediário,
recuperação de erro SQL na amostra, ausência de proteção contra snapshot nacional vazio e dependência
dos testes do fuso/ordem de execução. A versão anterior continua visível durante o staging; amostra,
ativação e remoção do snapshot anterior são transacionais. CLI e view usam `America/Sao_Paulo`.

A migração 0004 foi aplicada no banco local após um backup ser restaurado com sucesso em um banco
temporário (schema 0003, sem alterar o banco principal). Duas tentativas de snapshot nacional foram
interrompidas/fracassaram e limparam o staging. A segunda foi cancelada por decisão de escopo: não é
necessário varrer cerca de 484 mil atas (9.682 páginas no limite observado de 50 por página) para
avançar a F2. Nenhuma versão parcial foi publicada; não há atas TI carregadas. Não repetir a varredura
nacional. O retry de respostas transitórias permanece no commit `a1fc870`, mas isso não torna o
snapshot nacional necessário. A F2 ainda não passou o aceite: rotulagem, D6/G2 e F2B (itens/preços)
seguem pendentes. A migração 0003 permanece na cadeia por compatibilidade com o schema anterior.

Na preparação da F2B, o manual PNCP confirma `/itens` e `/itens/{numeroItem}/resultados` e define
`valorUnitarioHomologado` como preço do resultado. Porém, o retorno documentado não traz identificador
da ATA; contém `ordemClassificacaoSrp`. Não propagar preço para cada ATA da compra sem validar a
correspondência real; fallback honesto é manter o resultado no nível da compra.

Piloto direcionado da F2B: três compras-pai referenciadas por atas responderam 200 em
`/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}`; a rota `/itens` no mesmo host respondeu
404 para as três. Isso não demonstra ausência de itens na contratação: indica que host/rota precisam
ser confirmados contra o manual antes de implementar ingestão. Não iniciar varredura ou backfill para
investigar isso; usar uma compra conhecida e uma chamada de fumaça depois de identificar o host correto.

O log por página das atas TI tem retenção de 30 dias, aplicada no início de cada snapshot e limitada
à entidade `atas_ti_snapshot`; o índice da migração 0004 dá suporte à limpeza. Permanecem melhorias
operacionais medir duração real da carga e dimensionar a amostra de descartadas com intervalos de
confiança. A amostra inicial não comprova sozinha recall elevado de TI, uma classe rara no universo
nacional.

**Preparação da Fase 3:** o escopo foi alinhado em `docs/FASES.md`: consultas locais somente pela view
`v_atas_ti_vigentes`, SQL fixo/parametrizado e papel `mcp_reader`; nenhuma tool aceita SQL livre.
Preços dependem de F2B e “novas atas” será entendido como atas vigentes por data de publicação, sem
alegar histórico entre snapshots. `insumos/perguntas_reais.csv` ainda tem seis sugestões antigas e
precisa ser revisado/completado por Lucas até 20 perguntas reais. O prompt de abertura está pronto em
`docs/FASES.md`; usar depois do aceite de F2.

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

## PR aberto e backfill em andamento — 12/10/2026 (Claude/Sonnet 5)

- Verifiquei de forma independente o que o Codex relatou: `make test` 54/54 verde, árvore limpa,
  `.env` já com `PNCP_TI_IDENTITY_KEY` preenchida. Dei uma olhada direta em `src/pncp_ti/privacy.py`
  e na ADR 0013 (HMAC-SHA256 para identidade de fornecedor) — desenho são.
- Dei push na branch `feat/f1-base-historica` e abri o
  **PR #2**: https://github.com/lucaspagoti/pncp-ti-intel/pull/2. CI remoto verde nos 3 jobs
  (`test` — agora com serviço Postgres + `make migrate` antes do `pytest` —, `secrets-scan`,
  `vuln-scan`).
- Demonstrei parte do critério de aceite com uma consulta real: contratação de TI de 24/07/2023
  (implantação/customização de softwares pro Centro de Operações e Inteligência Municipal de
  Atibaia-SP, R$ 86,1 milhões, `numero_controle_pncp = 45279635000108-1-000671/2023`, fonte
  https://pncp.gov.br/app/editais/45279635000108/2023/671) — dado que já está fora da janela de
  365 dias do `compras-mcp` ao vivo, persistido e consultável localmente. Isso cobre a Lacuna 1.
- **Backfill completo rodando em background**, destacado desta sessão de chat (`setsid nohup ... &
  disown`), desde 12/10/2026 ~19:44. PID do processo Python: `332963` (via `uv run`, PID pai
  `332956`). Log em `logs/backfill-20261012T194453.log` (não versionado). Continua rodando mesmo
  que a sessão de chat termine ou o terminal seja fechado — só para com `kill 332963` (ou
  `pkill -f pncp_ti.ingest.cli`) ou naturalmente quando acabar.
  - Acompanhar progresso **sem gastar token/sem ler o log inteiro** — o log é enorme (vai passar de
    1,6M linhas): usar agregação SQL, nunca `cat`/`tail` do arquivo completo:
    ```sql
    SELECT entidade, status, count(*) AS paginas, sum(registros_gravados) AS gravados, max(concluido_em) AS ultimo
    FROM log_execucao_ingestao GROUP BY entidade, status ORDER BY entidade, status;
    ```
    (`docker exec pncp_ti_postgres psql -U postgres -d pncp_ti -c "..."`)
  - Abri uma aba do Terminal panel do app ("backfill progress") com essa mesma query em `watch -n 5`,
    pra o Lucas acompanhar sem passar por mim. Se essa aba já tiver sido fechada numa sessão nova,
    é só abrir de novo com o comando acima.
  - Ordem de processamento: `contratacoes` (13 modalidades × janelas de 365 dias desde 01/04/2023)
    primeiro, depois `atas`, depois `contratos` — ver `ADAPTADORES` em `src/pncp_ti/ingest/cli.py`.
    Em ~8 min já tinha 3.547 contratações gravadas, ainda na primeira entidade — é job de várias
    horas, principalmente por `contratos` (1,6M registros só em 9 meses de 2026, nacionalmente).
- **Pendente:** backfill terminar (acompanhar como acima); decidir com o Lucas se mergeia o PR #2
  antes ou depois do backfill completo (o critério de aceite da F1 em `docs/FASES.md` só fecha com
  backfill concluído — por paralelismo com a F0, a ideia é mergear/tagear junto da demonstração
  final, não antes). Depois disso: Fase 2 (precisa que o Lucas rotule
  `insumos/amostra_rotulada.csv`, mas esse arquivo só é gerado depois que eu montar o classificador —
  nada a fazer aí ainda).

**Próximo passo (superado — ver Fase 2A abaixo):** checar se o backfill terminou, decidir o timing do
merge/tag com o Lucas, e então propor o plano da Fase 2 em modo plan.

## Fase 2A — itens de contratação + regra de TI + amostra — 12/10/2026 (Claude/Sonnet 5)

Plano da Fase 2A proposto em modo plan e aprovado pelo Lucas (dividida em 2A/2B porque
`insumos/amostra_rotulada.csv` é gerado pelo sistema e rotulado à mão pelo Lucas no meio da fase — nada
do classificador/`evals`/normalização de preço pode começar antes disso). Implementado na branch
`feat/f2a-itens-filtro-ti` (aberta a partir de `feat/f1-base-historica`, não de `master` — `itens_contratacao`
não depende de FK em `contratacoes`, mas a decisão de compor sobre o branch da F1 em vez de esperar o
merge foi deliberada, ver abaixo).

**Achados reais por chamada direta à API (antes de fixar a migração — mesma disciplina da F1):**
1. Itens de contratação **não vêm embutidos** em `/v1/contratacoes/publicacao` — são endpoint separado.
   Dois caminhos no `compras-mcp`: um por-compra (`PNCPClient`, N+1 — inviável pro volume do backfill) e
   um paginado por janela de data (Dados Abertos, `DadosAbertosClient`,
   `/modulo-contratacoes/2_consultarItensContratacoes_PNCP_14133`). Escolhido o segundo — mesmo espírito
   do motor de janelas já existente, sem N+1. Lei 14.133-escopado, sem lacuna de cobertura (o backfill da
   F1 já começa em 01/04/2023, início da obrigatoriedade da 14.133).
2. `DadosAbertosClient` usa outro envelope (`resultado`/`totalPaginas` em vez de `data`/`totalPaginas`) e
   outros nomes/formato de filtro de data (`dataInclusaoPncpInicial/Final`, `yyyy-MM-dd`, não
   `dataInicial/Final yyyyMMdd`) que o `PNCPClient`. `ingerir_janela`/`_buscar_pagina`
   (`src/pncp_ti/ingest/executar.py`) ganharam dois parâmetros novos (`chave_dados`,
   `formatar_filtros_data`), com default = comportamento atual — `contratacoes.py`/`atas.py`/
   `contratos.py` não precisaram mudar.
3. Campos reais do payload de item (chamada direta, 12/10/2026): `numeroControlePNCPCompra`,
   `numeroItemCompra`, `descricaoResumida`, **`descricaodetalhada`** (minúsculo — outra inconsistência
   real do PNCP, igual ao `numeroControlePncpCompra` já documentado em `mapear_contrato`),
   `materialOuServico`, `codItemCatalogo`, `codigoGrupo`, `codigoClasse`, `unidadeMedida`, `quantidade`,
   `valorUnitarioEstimado`, **`valorTotal`** (não `valorTotalEstimado`), `valorUnitarioResultado`,
   `valorTotalResultado`, `codFornecedor`, `nomeFornecedor`, `situacaoCompraItem`, `temResultado`.
4. **`codFornecedor` existe e pode ser CPF** (11 dígitos, sem marcador de tipo — ao contrário de
   contrato/fornecedor, que trazem `tipoPessoa` junto) — contrariava a suposição inicial do plano ("item
   não tem CNPJ/CPF de fornecedor"). Corrigido durante a implementação: `mapear_item`/
   `extrair_fornecedor_de_item` inferem `tipoPessoa` pelo tamanho do documento (14 = PJ, 11 = PF) e
   reusam `identificar_fornecedor`/`mascarar_ni` (ADR 0013) via um payload-adaptador, sem tocar
   `privacy.py`. `itens_contratacao` ganhou `fornecedor_id`/`ni_fornecedor`, mesmo par de colunas que
   `contratos` (interno vs. mascarado exposto na view).
5. **Achado de qualidade de dado real, documentado e descartado como sinal:** o payload tem
   `itemCategoriaIdPncp`/`itemCategoriaNome` (ex. `"Informática (TIC)"`), que parecia à primeira vista o
   sinal perfeito pra regra de TI. Medido em ~700 itens reais de janelas e tipos de item bem diferentes
   (cabo elétrico, ar-condicionado, pasta de escritório, pinça cirúrgica) — **sempre** voltou
   `(3, "Informática (TIC)")`, inclusive pra item claramente não-TI. Campo não confiável (quebrado ou
   default no Dados Abertos); a regra (`classificar_por_regra`) não usa, só documenta o porquê.
6. CATMAT grupo 70 ("INFORMÁTICA - EQUIPAMENTOS, PEÇAS, ACESSÓRIOS E SUPRIMENTOS DE TIC") confirmado por
   chamada real como grupo inteiro de TI (16 classes, todas de equipamento/suprimento de informática,
   inclusive impressoras — convergente com o próprio exemplo do CLAUDE.md, "outsourcing de impressão").
   CATSER não tem grupo/seção equivalente sem falso positivo (ex. classe 8713 "manutenção de
   informática" está dentro de um grupo mecânico mais amplo) — por isso a lista de TI em serviços é por
   classe, não por grupo. Telefonia/internet (classes 1411-1414, 8411-8422) ficaram **fora** da lista
   confiante de propósito — decisão de negócio do Lucas, não fato de catálogo; caem em `INDEFINIDO` e a
   amostra rotulada decide.

**Entregue:**
- `db/migrations/versions/0003_itens_contratacao.py` — tabela `itens_contratacao` (chave natural
  `numero_controle_pncp || ':' || numero_item`, sem FK pra `contratacoes` — mesma decisão já tomada pra
  `contratos.numero_controle_pncp_compra`/`atas.numero_controle_pncp_compra` na migração 0001, pelo
  mesmo motivo: o item pode ser ingerido fora de ordem da compra-pai), view `v_itens_contratacao`
  (exclui `raw` e `fornecedor_id`, expõe `ni_fornecedor` mascarado — mesmo padrão de `v_contratos`).
- `src/pncp_ti/ingest/mapeadores.py`: `mapear_item`, `extrair_fornecedor_de_item`.
- `src/pncp_ti/ingest/executar.py`: generalização mínima (`chave_dados`, `formatar_filtros_data`).
- `src/pncp_ti/ingest/client.py`: `criar_cliente_dados_abertos`.
- `src/pncp_ti/ingest/itens.py` (novo adaptador) + `cli.py` (`ADAPTADORES["itens"]`, mapa `CLIENTES`
  por entidade — itens usa `DadosAbertosClient`, as outras três `PNCPClient`, então `_rodar()` abre o
  cliente certo por entidade em vez de um só pro run inteiro).
- `src/pncp_ti/classificar/regra.py` (`classificar_por_regra`, tri-estado `TI`/`NAO_TI`/`INDEFINIDO`) e
  `src/pncp_ti/classificar/amostra.py` (`make amostra` → `insumos/amostra_rotulada.csv`, cabeçalho já
  fixo, amostra estratificada ~50 por estrato, `rotulo_lucas`/`categoria_ti`/`observacao` em branco).
- Testes novos: `test_mapeadores.py` (item com CNPJ, item com CPF mascarado, item sem resultado, CPF
  solto em texto livre sanitizado), `test_ingest_upsert.py` (idempotência de `itens_contratacao` com
  cliente falso no formato Dados Abertos), `test_classificar_regra.py` (um caso por ramo),
  `test_classificar_amostra.py` (estratificação, cabeçalho exato do CSV), `test_ingest_cli.py` (cliente
  por entidade — um teste existente precisou trocar de monkeypatchar `criar_cliente` pra monkeypatchar
  `CLIENTES`, já que o dict agora é resolvido em tempo de definição do módulo). `make test`: 72/72 verde.
- Validação real feita e depois revertida de propósito (mesma prática da F1): `make migrate` aplicado no
  Postgres de desenvolvimento (não quebra o backfill da F1 em andamento — só `CREATE TABLE`/`VIEW`/
  `GRANT` novos); chamada real de `itens.ingerir` numa janela de 2 dias (01-02/06/2024) gravou 10 itens
  reais com `fornecedor_id`/`ni_fornecedor` corretos (CNPJ intacto, sem CPF vazado); reprocessar a mesma
  janela manteve a contagem (idempotência); `TRUNCATE itens_contratacao` + limpeza do log depois,
  deixando o banco de volta vazio pro Lucas decidir quando rodar o backfill de itens de verdade.
  `make amostra` testado contra a tabela vazia (0 linhas, cabeçalho correto, sem erro) — a amostra com
  conteúdo real só existe depois do backfill de itens rodar.

**Pendências de propósito fora do escopo desta sessão:**
- Backfill completo de itens (01/04/2023 até hoje) não rodado — decisão do Lucas, mesmo raciocínio da
  F1 (job longo, nacional).
- `make amostra` com conteúdo real não gerado (depende do item acima).
- Fase 2B (classificador local scikit-learn, `evals/`, normalização de preço por unidade) não iniciada —
  depende do Lucas rotular a amostra real.
- Nenhum PR aberto ainda pra esta branch.

**Revisão independente feita nesta sessão** (8 ângulos via subagentes — correção, comportamento
removido, cross-file, reuso, simplificação, eficiência, altitude, convenções do CLAUDE.md — mesmo
protocolo usado nas revisões da F0/F1). Achados reais, corrigidos na mesma branch (commit separado):
- `_buscar_pagina` (quirk do 204 vazio) ainda devolvia a chave hardcoded `"data"`, ignorando o
  `chave_dados` novo — uma janela de itens genuinamente vazia (caso normal antes do backfill) quebrava
  a ingestão inteira em `ValueError`, não só a entidade `itens`. Corrigido: o fallback agora usa
  `chave_dados`. Teste de regressão novo (`test_itens_janela_sem_resultado_204_nao_quebra_a_ingestao`).
- `_tipo_pessoa_por_digitos` devolvia `None` pra documento com contagem de dígitos ambígua (nem 11 nem
  14) — `mascarar_ni(ni, None)` interpretava isso como "não é CPF, não mascarar" e deixava passar o
  documento crú. Risco real de violar a regra fixa "CPFs sempre mascarados" pra um `codFornecedor`
  mutilado. Corrigido: ambíguo agora vira `"PF"` (lado seguro — mascara por padrão); só 14 dígitos
  limpos confirma CNPJ. Teste de regressão novo.
- `classificar_por_regra` tratava qualquer campo de catálogo não-nulo (até só `codigo_item_catalogo`)
  como "catálogo conhecido" e caía em NAO_TI com confiança mesmo sem o campo que a decisão de verdade
  usa (`codigo_grupo`/`codigo_classe` nulo, ou `material_ou_servico` ausente/corrompido — lacuna de
  qualidade de dado real já documentada nesta mesma sessão). Corrigido: só decide por catálogo quando o
  par material/campo específico está completo; senão cai pra palavra-chave como se não houvesse
  catálogo. Dois testes de regressão novos.
- `amostra.py` carregava a tabela `itens_contratacao` inteira na memória (sem `LIMIT`) antes de
  amostrar ~150 linhas, e fazia `shuffle` completo de cada estrato. Inofensivo hoje (tabela vazia), mas
  real depois do backfill de itens rodar (mesma escala de milhões de linhas já vista em `contratos` na
  F1). Corrigido: `ORDER BY random() LIMIT 60000` no Postgres antes de amostrar, e `random.sample` em
  vez de `shuffle`+slice.
- Achados de menor severidade, documentados e **não corrigidos** (decisão, não esquecimento):
  colisão rara de escopo HMAC em `identificar_fornecedor` quando `numeroControlePNCPCompra` falta E o
  documento é malformado (duplo requisito, baixa severidade); `cli.py` abre um cliente HTTP por
  entidade em vez de um só pro run inteiro (overhead pequeno, só por execução, não por janela);
  duplicação da fixture de teste `ClienteDadosAbertosFalso`/`ClientePNCPFalso`; `_tipo_pessoa_por_digitos`
  reimplementa a inferência PJ/PF por contagem de dígitos que `mask.py`/`privacy.py` já fazem cada um
  independentemente (três cópias agora) — risco só se a convenção de dígitos mudar.
- Zero violações de `CLAUDE.md` confirmadas (checado explicitamente: cliente reusado do `compras-mcp`
  pra Dados Abertos, nenhuma tool MCP nova/duplicada, máscara de CPF, segredos, stdio/127.0.0.1).

`make test`: 76/76 verde depois das correções (72 antes + 4 testes de regressão novos).

**Próximo passo:** Lucas decide quando rodar o backfill de itens (`--entidades itens`, ou junto do resto
numa nova rodada de backfill), e se/quando comitar e abrir PR desta branch. Depois do backfill,
`make amostra` de verdade, e só então propor o plano detalhado da Fase 2B.

### Revisão Codex da F2A — 12/10/2026 (supersede o próximo passo acima)

**Veredito: corrigir antes de backfill completo e aceitação.** `make test` executado novamente:
76 aprovados, 2 avisos de dependência. Revisão independente adicional em leitura e reproduções
sintéticas confirmaram lacunas não cobertas pelos testes atuais:

- P1: `raw.codFornecedor` permanece integral para documentos ambíguos de 10/13 dígitos e CPF
  numérico de 11 dígitos. A máscara da coluna não sanitiza esse campo no JSON bruto.
- P1: diário de itens filtra inclusão e não reconcilia homologação/alteração de item antigo.
  Evidência real: itens 1/2 de `00394452000103-1-009427/2024`, incluídos em 01/06/2024,
  atualizados em 21/03/2025. Verificar uso do filtro upstream `dataAtualizacaoPncp`.
- P2: fornecedores com documento incompleto e mesma máscara colidem entre itens da mesma compra,
  mesmo com número PNCP preenchido. Escopo ambíguo precisa compra + item; CPF completo continua global.
- P2: CSV não inclui chave/número do item e sobrescreve arquivo existente, apagando rótulos humanos.
- P2: telefonia/internet documentadas como `INDEFINIDO` caem em `NAO_TI` (classe 8411 reproduzida).
- Cobertura nacional ainda não demonstrada. Dez itens do módulo Dados Abertos em dois dias não
  provam equivalência ao PNCP. Comparação independente encontrou contratações municipais no PNCP
  na mesma janela, mas datas de publicação/inclusão diferem: tratar como indício e validar por
  identidade de compras, esfera e plataforma antes de afirmar cobertura ou carregar todo histórico.

**Sequência recomendada:** corrigir achados com regressões, comprovar cobertura e registrar ADR da
fonte; fazer piloto delimitado e diverso para gerar amostra identificável sem exigir backfill completo;
preparar commits e PR F2A dependente da F1, depois rotulagem e plano F2B. Não mergear como fase aceita
com achados abertos. `logs/` não rastreado deve ficar fora dos commits. Melhorar metadados/seed e
amostragem por estrato; limite SQL atual limita memória Python, não custo de varrer a tabela.

Nesta revisão não foram alterados código funcional ou dados persistentes, iniciado backfill, feito
TRUNCATE, commit ou PR. Relatório detalhado da sessão:
`/home/lucas/Documents/Codex/2026-10-12/em-home-lucas-projetos-pncp-ti-5/outputs/revisao-f2a.md`.

### Mudança de escopo — ADR 0015 — 12/10/2026 (Claude/Opus 5.5) — SUPERSEDE TUDO ABAIXO SOBRE F1/F2A

Decisão do Lucas: **só TI e só atas vigentes**, sem "pesquisa infinita". Feito:
- Backfill nacional **parado** (PIDs 332963/332956). 82.780 contratações ficaram no banco de dev,
  que será limpo na migração da F2A. Aba "backfill progress" fechada.
- Medido por chamada real: `/v1/atas` com janela de 1 dia = 484.081 atas vigentes; página
  limitada a 50 (pedir 500 devolve 50), ~9.700 páginas, ~80 min por snapshot.
- ADR 0015 criada. ADR 0014 marcada substituída. ADRs 0003/0005/0006 com status atualizado.
  `docs/PLANO.md`, `docs/FASES.md` (F1 = infraestrutura pronta pra merge; F2 = 2A atas TI
  vigentes, 2B itens/preços), `CLAUDE.md` (objetivo e comandos) e README atualizados.
- **Código ainda não mudou.** A working tree tem a F2A antiga (itens via Dados Abertos, migração
  0003 aplicada no dev) sem commit.

**Próximo passo:** Lucas aprova o plano. Depois: merge da F1 (PR #2), e a F2A nova em modo plan:
snapshot de atas + filtro de TI + view `v_atas_ti_vigentes`, remoção de contratações/contratos/itens,
e reaproveitamento de `regra.py`/`amostra.py`/`executar.py`.

### Correções Codex da F2A — 12/10/2026

Lucas autorizou: “pega você pra corrigir as falhas [...] a questao de mascara nao vi problema,
ja sao dados publicos. De resto, pode arrumar”. A sanitização/máscara permanece como estava;
esse achado ficou explicitamente fora desta correção, por instrução do usuário. Não interpretar
esta sessão como aprovação para remover as máscaras existentes da F1.

**Corrigido:**
- Diário explícito de itens (`--diario --entidades itens`) também reconcilia itens antigos desde
  `backfill_start`, em janelas de inclusão de 30 dias, com `dataAtualizacaoPncp >= início do diário`.
  Semântica de limite inferior inclusivo confirmada em consulta real. Janela de 365 dias expirou;
  janela de 30 dias respondeu rapidamente. Custo depende da história configurada (~43 janelas hoje);
  filtro não tem teto de atualização: consulta retrospectiva pode trazer estado mais recente.
- Documento incompleto/mascarado usa HMAC com compra + item; CPF completo mantém HMAC global.
  Número do item é canônico e validado: rejeita booleano, decimal, zero e negativo.
- CSV inclui `chave` e `numero_item`, recusa sobrescrita e oferece `--saida`/`--seed`.
  CLI não cria CSV vazio. Amostragem por reservoir em cada estrato, cursor no servidor e ordem
  estável substituem o corte aleatório de 60 mil candidatos; memória limitada ao tamanho da amostra.
  Contagens da população por estrato são apresentadas no comando. Custo ainda inclui ler a população.
- Telefonia/internet pendentes retornam `INDEFINIDO`; código de catálogo zero/negativo/inválido
  usa fallback textual. Códigos genéricos positivos precisam de avaliação posterior.
- Itens ficam fora das entidades padrão da F1. `--ate` permite piloto delimitado de backfill e
  validação do intervalo; `logs/` e variantes `amostra_rotulada*.csv` ficam fora do Git.
- ADR 0014, README, FASES e PLANO registram origem complementar e limites de cobertura.

**Cobertura nacional de itens continua não demonstrada:** comparação por CNPJ sem datas falhou
inclusive no controle positivo; consultas anuais e itens PNCP por compra expiraram. Isso não
comprova exclusão de municípios nem equivalência nacional. Não liberar backfill de itens como base
nacional sem repetir ensaio válido por compra/plataforma. Pipeline nacional por compra PNCP com
enriquecimento Dados Abertos, se necessário, é próximo trabalho; não foi implementado nesta correção.

Revisão independente das correções sem achados bloqueantes; regressões incluem Postgres em banco
UUID isolado, atualização tardia de preço/fornecedor, dupla execução idempotente, cursor real com
item sem compra-pai, preservação dos rótulos e separação de identidades. Resultado final dos testes
`make test`: lint/format aprovados, 112 testes aprovados, 2 avisos de dependência, 19,78 s;
`git diff --check` aprovado. Nenhum dado de desenvolvimento foi alterado, nenhum
backfill iniciado/interrompido, commit ou PR criado. Próximo passo: piloto delimitado após escolha
do período e verificação de cobertura; rotular amostra e seguir ao plano F2B. Esta correção deixa
a F2A revisável, mas não demonstra o portão G2 nem encerra a F2.

Relatório: `/home/lucas/Documents/Codex/2026-10-12/em-home-lucas-projetos-pncp-ti-5/outputs/correcoes-f2a.md`.

### Escopo confirmado pelo Lucas — 12/10/2026

Lucas reforçou que o backfill foi cancelado e que o foco é **somente atas de registro de preços de
TI vigentes**. A decisão normativa já está na ADR 0015; README, CLAUDE.md, PLANO e FASES também
registram o cancelamento. Esta confirmação substitui os próximos passos dos relatórios anteriores
que sugeriam piloto/backfill de itens ou validação da cobertura Dados Abertos.

Não continuar consultas de cobertura de itens nem executar os comandos antigos de ingestão nacional.
A reimplementação da F2A começou na branch `feat/f2-atas-vigentes-ti`: snapshot diário de `/v1/atas`,
filtro de TI na entrada, amostra das descartadas e view das atas vigentes. A migração destrutiva não
foi aplicada ao banco e o snapshot real não foi iniciado. O backfill histórico permanece cancelado.

### Continuação da implementação da F2A — 12/10/2026

- Normalizei datas `date` da API PNCP antes do INSERT (inclui payloads com timestamp); a coluna
  `raw` continua guardando o payload sanitizado original.
- Deduplicação por `numeroControlePNCPAta` em toda a paginação evita contagens/amostras duplicadas.
  A API usa paginação por offset sobre dados mutáveis, então alteração durante a carga ainda pode
  causar omissão; não há cursor consistente oferecido pelo endpoint.
- Ampliei o filtro para incluir `microinformática` e o termo delimitado `TIC`.
- Corrigi o fuso explicitamente: host em `America/Sao_Paulo` estava no dia 12 e Postgres em UTC já
  no dia 13; a view excluía itens vigentes na virada. CLI e view agora usam a data de Brasília.
- A migração 0004 foi testada num banco descartável preenchido com registros sintéticos no schema
  até 0003; confirmou remoção das tabelas antigas/dados locais e a criação da nova view. Foi teste
  isolado: o banco de desenvolvimento segue sem alterações.
- `make test`: 73/73; inclui chamada leve read-only do PNCP e do `compras-mcp`. Dois avisos de
  depreciação de dependências. `git diff --check` também passou.
- Nenhum commit, push, PR, migração no banco de desenvolvimento ou snapshot nacional foi feito.

**Falta antes de considerar a F2A revisada:** revisão independente por subagente; resolver achados,
se houver. Depois, Lucas pode demonstrar o critério de aceite. A retenção do log por página, apontada
na revisão inicial (~9.700 registros por snapshot diário), foi implementada com janela de 30 dias.

### Revisão Codex da implementação do Luna — 12/10/2026

Lucas pediu revisão e autorizou PR se o desenho fosse aprovado. **Veredito: aprovado para PR após
correções**, com aceite operacional/rotulagem ainda pendentes. Revisão realizada diretamente pelo
Codex, reavaliando o trabalho do Luna. Relatório: `docs/REVISAO-F2A.md`.

Reproduzidos e corrigidos: 204 intermediário publicava carga parcial; INSERT inválido na amostra
impedia limpeza e liberação do lock; CSV podia interpretar objeto externo como fórmula. Corrigidos
os testes dependentes de fuso/ordem e recuperada cobertura de paginação/retries removida na troca
de adaptadores. Novas regressões exercitam concorrência, publicação/rollback, vigência, cancelamento,
reclassificação, amostragem e preservação da versão anterior.

`TZ=UTC make test`: **103 aprovados**, lint/format verdes, dois avisos de dependências;
`git diff --check` aprovado. A F1 foi confirmada mergeada no GitHub (PR #2), e esta branch foi
atualizada por fast-forward para `origin/master` antes do commit da F2A. A migração 0004 continua
sem aplicação no banco de desenvolvimento; nenhum backfill ou snapshot nacional foi iniciado.

Melhorias registradas: retenção de 30 dias para o log por página (implementada em commit posterior),
medição do custo real da carga e amostra com intervalos de confiança antes de declarar atingidas as
metas D6/G2.

PR aberto: https://github.com/lucaspagoti/pncp-ti-intel/pull/3. Commit de implementação `6d7bd23`.
Varredura local `pre-commit run gitleaks --all-files` aprovada; CI remoto iniciado no PR.
Não houve merge, migração de desenvolvimento ou carga nacional nesta revisão.
