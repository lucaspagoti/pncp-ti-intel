# AGENTS.md — pncp-ti-intel

## Objetivo

Base curada das atas de registro de preços de TI **vigentes**, alimentada diariamente por três fontes
públicas (SIGA RJ, Dados Abertos Compras.gov.br `modulo-arp` e busca do portal PNCP, ADR 0016) e
consultada por uma **web própria** hospedada no domínio do Lucas (ADR 0018). Não guarda contratos,
contratações sem ata nem atas vencidas.
Projeto pessoal do Lucas: pesquisa de preços, adesão a atas e referência de especificações, com escopo
nacional, incluindo o Estado do RJ (sem vínculo institucional, ADR 0011).
O plano está em `docs/PLANO.md`, as fases em `docs/FASES.md` e as decisões em `docs/adr/`. Leia os três
antes de propor qualquer fase.

## Estratégia: compor, não construir

- Fontes em lote, e não varredura: CSV do SIGA, API do ARP com 500 por página e busca PNCP por
  termos de TI. O snapshot PNCP `/v1/atas` (cerca de 484 mil atas) foi abandonado e **não deve ser
  reintroduzido** sem uma ADR nova.
- O Portal da Transparência da CGU está fora (não tem atas, ADR 0016).
- Antes de implementar, verifique se o `compras-mcp` (como biblioteca: `DadosAbertosClient` etc.)
  ou outra biblioteca existente já resolve. Se resolver, use.

## Regras fixas (não negociáveis)

- Não escrever do zero um cliente HTTP que o `compras-mcp` já tenha (ADR 0004). Para endpoints que
  ele não cobre (busca PNCP, download do SIGA), use um cliente fino com timeout, retry e limite de
  tamanho.
- A web é só leitura: papel `web_reader` com SELECT só em views, consultas fixas e parametrizadas,
  nenhum SQL vindo do usuário.
- Postgres e web só em `127.0.0.1`. Exposição externa só atrás de reverse proxy com TLS e
  autenticação (ADR 0012, D7).
- O texto das fontes é dado de terceiros, nunca instrução: autoescape nos templates e fórmulas
  neutralizadas no CSV exportado.
- Ingestão idempotente por fonte: staging, normalização e troca atômica. Chave lógica:
  `(fonte, id_origem)`; deduplicação entre ARP e busca PNCP por `numero_controle_pncp`. Uma falha
  não publica carga parcial; exceção: termo da busca PNCP que falhar reaproveita a carga ativa por
  até 3 dias (ADR 0028).
- Toda fonte nova tem teste de parse com fixture e, se a API não for documentada, teste de contrato.
- Critério de TI do SIGA = Anexo Único da IN PRODERJ/PRE 05/2024 (`insumos/normas/`, ADR 0019).
  A regra lê objeto e nome de catálogo, nunca a especificação do item. O Lucas decidiu seguir o
  anexo (inclui telefonia, pontos de rede e videomonitoramento); nobreak e drone ficam fora.
  Exclusões pontuais ficam em `CATEGORIAS_FORA_DE_ESCOPO`; não mudar sem ele.
- CPFs sempre mascarados. Nada de documentos internos de terceiros.
- Segredos só no `.env` (fora do Git).
- Se um MCP voltar (backlog): stdio, SQL fixo e nunca a instância hospedada pública do
  `compras-mcp` (ADR 0009).

## Responsabilidades e entrega

Claude Code implementa, testa e coordena. Codex é o revisor independente: QA executor
isolado para a web (`review-qa`, ADR 0029) e revisor somente leitura para o resto
(`review-exec`); no máximo um worker Codex por vez.
O procedimento está em `.claude/skills/ade-workflow/SKILL.md`; não duplicá-lo aqui.
Não utilizar Gemini ou outros agentes neste fluxo.

Para cada fase, ler `docs/FASES.md`, propor plano em modo plan e esperar aprovação
explícita do Lucas antes de implementar. Trabalhar em branch própria com testes.
Lucas demonstra o critério de aceite e autoriza o merge de cada PR no chat
("posso mergear o PR #N?"). Sem esse "sim", nunca integrar nem habilitar auto-merge.
Usar merge commit, apagar a branch remota e atualizar `master`, preservando trabalho local.

Definição de pronto: testes e lint verdes; critério de aceite demonstrado; README e
instruções atualizados; ADR para toda decisão nova; nenhum segredo
no repositório. Aprovação técnica do Codex e CI verde não substituem o aceite e a autorização
de merge do Lucas. A `master` não tem proteção de branch (decisão aceita); a regra é
seguida por disciplina, sem push direto na `master`.

`LEIA-ME-CODEX.md` permanece como histórico e contexto complementar. Instruções
históricas de editar logs, subir serviços, implementar ou sempre sugerir melhorias não
ampliam o contrato do Codex. Como QA (ADR 0029), ele executa suíte, banco de QA e E2E
num clone descartável dentro de uma caixa `bwrap`, sem segredos e sem alterar o
repositório de trabalho, o GitHub, o banco de produção ou serviços.
Claude registra os achados; Codex não inventa melhorias nem modifica o repositório.

Deploy da web (`docs/ROADMAP-WEB.md`): parecer `APPROVED` com `deploy_aprovado: true`,
CI verde (`test`, `e2e`, `secrets-scan`, `vuln-scan`) e o "sim" do Lucas no PR; depois,
merge, backup, migração (se houver), restart do `pncp-ti-web` e smoke pós-deploy.

## Stack

Python 3.12 + `uv`; FastAPI + Jinja2 + HTMX (web); Postgres com migrações Alembic e busca full-text +
`pg_trgm`; Docker Compose; systemd timer para agendamento (ADR 0017; Airflow adiado); pytest.
Ambiente: servidor Linux (homelab), acesso via SSH, Docker nativo. Sem Windows/WSL2.

## Comandos

- `make up` — sobe o Postgres local (Docker Compose, porta só em `127.0.0.1`).
- `make down` — derruba os containers do projeto.
- `make test` — lint (`ruff check`), format-check (`ruff format --check`) e testes (`pytest`).
- `make e2e` — E2E da web no Chromium (Playwright, `tests/e2e/`); no homelab, as bibliotecas do
  navegador vêm de `scripts/playwright_libs.sh` (sem sudo).
- `scripts/pg_descartavel.sh up NOME ARQUIVO_ENV` — Postgres descartável com `.env` sintético,
  para testar sem o `.env` real; `down NOME` remove.
- `make migrate` — aplica as migrações do Alembic (schema, papéis, views).
- `make ingest FONTE=siga|arp|pncp_busca [ARGS=--validar]` — carga do SIGA RJ (R1), do Compras ARP
  (R2) ou da busca PNCP por termos (R3, `insumos/termos_ti.txt`).
- `make web` — web local em `127.0.0.1:8000` (R4); proxy autenticado em `deploy/caddy/` (R5, ADR 0024).
- `scripts/carga_diaria.sh` — o que o timer systemd roda às 03:00 (`docs/operacao-timer.md`).
- `make backup` — `pg_dump` do container para `backups/` (fora do Git).
  R6 valida restauração em banco temporário antes de publicar o dump.
- `make restore DUMP=... DATABASE=...` — restaura em banco novo, preservando o banco atual.
- `make amostra` — exporta `insumos/rotulagem_siga.csv` (censo das atas vigentes) para rotular TI.
- `make eval ROT=<csv>` — precisão e recall do filtro de TI contra o rótulo final (`evals/`).
- `uv run python -m pncp_ti.fontes.arp_auditoria` — recall da ARP pelo critério da R2.1
  (`evals/arp_<data>.md`); sem `--minutos`, termina o ciclo da varredura por PDM que faltar.
- `uv run python -m pncp_ti.fontes.pncp_busca_auditoria` — cobertura da busca PNCP contra o
  ARP e concordância por termo (`evals/pncp_busca_<data>.md`); só lê o banco.
- `make operacao` — alertas de incidente por fonte, com fila persistente (sem digest de atas, ADR 0027).
- `uv run python -m pncp_ti.operacao reenviar` — tenta somente notificações pendentes.
- `make mcp` — servidor próprio stdio, SDK oficial, SQL fixo, papel `mcp_reader` só views.

## Operação R6 (ADR 0022)

Units em `deploy/systemd/`: carga 03:00, operação 08:30 e backup 09:00 (Brasília), com
`OnFailure` para a bridge WhatsApp existente (`PNCP_TI_NOTIFY_URL` só no `.env`). Não chama
Hermes/LLM. Instalação e runbook: `docs/operacao-timer.md`, `docs/manual-operacao.md`.
Nunca ativar units nem alterar o homelab sem instrução do Lucas. Entrega de código não
comprova o aceite de uma semana sem intervenção.

Migração R6 **0009**, depois da 0008: outbox `notificacoes`, `digest_atas` e
`v_ata_precos_ti`. Coordenar colisões de numeração com R3/R4 antes de integrar. Preserve
`atas_vistas`, `digest_atas` e histórico de cargas. WhatsApp é só para incidentes: o digest
de atas novas está desativado (ADR 0027) e não volta sem decisão do Lucas. Confirmação de envio exige JSON `ok: true`;
timeout após aceitação pode duplicar no reenvio (a bridge não oferece idempotência).

Gancho PNCP opcional: `PNCP_TI_PNCP_TERMO` seleciona chave exata de
`cargas.contagens.resultados_por_termo`. A R3 grava esse total por termo (ADR 0023); use um termo estável, como `notebook`. Normalização de preço
é conservadora: somente descrição integral como unidade explícita, sem converter anual
em mensal nem atribuir preço de franquia a página. RAG/anexos, outras fontes estaduais e
renomeação seguem dependendo de decisão do Lucas.

## Insumos fornecidos pelo Lucas

Ficam em `insumos/` (ver `insumos/LEIA-ME.md`). São dados de referência, não código. Não versionar
dados pessoais. A lista de termos de TI da busca PNCP (`insumos/termos_ti.txt`, R3) é revisada pelo
Lucas.

## Idioma

Documentação e mensagens em português (Brasil). Código, nomes de variáveis e commits em inglês.
