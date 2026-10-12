# pncp-ti-intel — pacote inicial

Projeto pessoal: base de inteligência de contratações públicas de TI, alimentada pelo PNCP (escopo
nacional) e consultada via MCP.
Este pacote contém só documentos e configurações de partida. Nenhum código ainda: o código nasce na Fase 0, com o Claude Code.

Plano completo (versão viva, editável): https://claude.ai/code/artifact/b89bd04f-c28e-4fbc-9bd9-f46c9c95aea4
Cópia estática do plano: `docs/PLANO.md`.

## O que tem aqui

| Caminho | Para quê | Quem usa |
| --- | --- | --- |
| `CLAUDE.md` | Regras e contexto que o Claude Code lê em toda sessão | Claude Code |
| `docs/PLANO.md` | Plano completo: escopo, arquitetura, segurança, roadmap | Você e o Claude Code |
| `docs/adr/` | As 9 decisões de arquitetura já tomadas | Claude Code |
| `docs/FASES.md` | Entregas, critérios de aceite e prompt de abertura de cada fase | Você |
| `docs/GLOSSARIO.md` | Termos de contratação pública usados no código | Claude Code |
| `docs/referencias/LINKS.md` | Fontes oficiais e de terceiros | Ambos |
| `scripts/baixar_referencias.ps1` | Baixa as especificações OpenAPI do PNCP e a documentação do compras-mcp | Você (uma vez) |
| `insumos/` | Modelos de planilha que **só você** pode preencher | Você |
| `.mcp.json` | Registra o compras-mcp local (stdio, versão fixada) | Claude Code |
| `.env.example`, `.gitignore` | Base de configuração segura | Claude Code |
| `src/pncp_ti/` | Código da ingestão (Fase 1) — schema, upsert, adaptadores por entidade, CLI | Claude Code |
| `db/migrations/` | Migrações Alembic (schema, papéis `ingest`/`mcp_reader`, views) | Claude Code |
| `scripts/backup_postgres.sh` | `pg_dump` diário do Postgres local | Você (cron no homelab) |

## Status

**Fase 0 (Fundação) concluída**, tag `f0-fundacao`. **Fase 1 (Base histórica) em andamento**: schema
(Alembic), papéis `ingest`/`mcp_reader`, ingestão idempotente (diária + backfill) de contratações, atas
e contratos do PNCP. Ver `LEIA-ME-CODEX.md` para o handoff detalhado e `docs/FASES.md` para os critérios
de aceite de cada fase.

D1 (GitHub privado pessoal) e D2 (servidor Linux via SSH, sem WSL2) resolvidas — ver `docs/adr/` e
`LEIA-ME-CODEX.md`.

## Como rodar

```
cp .env.example .env   # preencha senhas e PNCP_TI_IDENTITY_KEY antes de usar
make up                # sobe o Postgres local
make migrate            # aplica o schema (tabelas, papéis ingest/mcp_reader, views)
make test               # lint + testes (inclui compras-mcp e PNCP reais)
```

## Identidade e privacidade

Gere `PNCP_TI_IDENTITY_KEY` com `python -c "import secrets; print(secrets.token_hex(32))"`
e copie o resultado para `.env` (permissão `0600`). CPF completo só é usado em memória para gerar
HMAC-SHA256; máscara e identidade são campos separados. Identificadores já mascarados na origem
ficam isolados por contrato, pois não comprovam identidade global. CNPJ público permanece íntegro.
Guarde a chave com o backup cifrado de configuração; alterá-la requer plano de migração/reingestão.

A migração `0002` preserva registros legados, limpa CPF dos textos/JSON e remove vínculos ambíguos
com fornecedores PF. Reingerir contratos preenche a identidade correta; máscara antiga não permite
reconstruir CPF nem desfazer uma fusão anterior. A migração não apaga o banco.
Campos/textos com sequências isoladas de 11 dígitos são mascarados conservadoramente (podem incluir
telefones/códigos); valores numéricos de preços permanecem numéricos. Erros de itens preservam os
itens válidos, mas fazem o job retornar código não zero. Logs não incluem payloads/tracebacks.

## Ingestão (Fase 1)

```
make ingest             # diário: janela de ontem até hoje, todas as entidades
make ingest-backfill    # histórico: desde INGEST_BACKFILL_START (.env) até hoje — job longo
make backup             # pg_dump para backups/ (fora do Git)
```

`make ingest-backfill` cobre contratações, atas e contratos nacionalmente desde 01/04/2023 (início da
obrigatoriedade do PNCP para a Lei 14.133/2021) — é um job de horas, não minutos: só contratos teve mais
de 1,6 milhão de registros em 9 meses de 2026, nacionalmente. É seguro interromper (Ctrl-C) e rodar de
novo: as janelas são reprocessadas desde a primeira página e os upserts evitam duplicações.
Não pulamos offsets antigos porque a fonte é mutável. `log_execucao_ingestao` registra resultados
por página e permite acompanhar erros (ADR 0005 e 0013). No diário, contratações também
consultam o endpoint de atualizações, cobrindo mudanças de publicações antigas. Para acompanhar o progresso enquanto
roda:

```sql
SELECT entidade, status, count(*), max(concluido_em)
FROM log_execucao_ingestao
GROUP BY entidade, status
ORDER BY entidade, status;
```

Para rodar só uma entidade: `uv run python -m pncp_ti.ingest.cli --backfill --entidades contratacoes`.
Itens de contratação (preço por unidade) não entram na Fase 1 de propósito — só a Fase 2, e só para as
contratações que o classificador de TI marcar como relevantes (ver `docs/FASES.md`).

### Backup diário e restauração segura

O backup usa `pg_dump` dentro do container Postgres (mesma versão do servidor), valida o
arquivo e publica o nome final por rename atômico. Arquivos têm permissão `0600`; falhas
removem somente o arquivo parcial. O `.env` nunca é executado pelo shell.

Para agendar diariamente às 03:00 no fuso do servidor, adicione manualmente ao `crontab -e`
(agendamento documentado, não ativado por estes scripts):

```cron
0 3 * * * cd /home/lucas/projetos/pncp-ti-intel && ./scripts/backup_postgres.sh >> backups/cron.log 2>&1
```

Crie antes o diretório `backups` com permissão `0700`, proteja o log e garanta que `docker`
e `uv` estejam no PATH do cron. Defina uma política de retenção conforme o espaço disponível.

Teste o restore em um banco **novo**, sem apagar volume ou dados atuais:

```sh
make restore DUMP=backups/<arquivo>.dump DATABASE=pncp_restore_validacao
```

O script recusa o banco atual, bancos de sistema e qualquer destino já existente. Valida
primeiro o dump, provisiona papéis globais ausentes através de migrações em banco descartável
separado e restaura no destino vazio com `--exit-on-error --single-transaction`. `pg_dump`
não inclui papéis globais; em outro servidor, configure as três senhas no `.env` antes de
restaurar. Guarde também uma cópia cifrada do `.env` separada do dump: a
`PNCP_TI_IDENTITY_KEY` é necessária para manter a identidade HMAC dos fornecedores PF
nas próximas ingestões e deve ser preservada entre servidores. Papéis já existentes preservam suas senhas. Uma falha nunca apaga o banco atual;
o novo destino fica disponível para diagnóstico. Verifique contagens e consultas no novo
banco antes de considerar uma troca, que deve ser feita separadamente.

## Antes de abrir o Claude Code (pacote original — já feito nesta instância)

1. Descompacte esta pasta onde o projeto vai morar e rode `git init`.
2. Rode `scripts/baixar_referencias.ps1` (PowerShell) para baixar as referências oficiais para `docs/referencias/`.
3. Responda as decisões D1 e D2 (ver `docs/PLANO.md`, seção "Decisões pendentes").
4. Preencha o que der em `insumos/` — veja `insumos/LEIA-ME.md` (nada bloqueia o início das fases).
5. Abra o Claude Code na pasta e cole o prompt da Fase 0 de `docs/FASES.md`.

## Finalidade do tratamento de dados (LGPD)

Esta base trata exclusivamente dados públicos divulgados no PNCP, com a finalidade de uso pessoal de
pesquisa e aprendizado (pesquisa de preços, adesão a atas e referência de especificações). CPFs são
mascarados. Nenhum documento interno de terceiros é armazenado aqui.
