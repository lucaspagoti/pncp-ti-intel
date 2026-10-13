# pncp-ti-intel

Projeto pessoal: base local de atas de registro de preços de TI vigentes, alimentada pelo PNCP
(escopo nacional) e consultada via MCP.

Plano completo (versão viva, editável): https://claude.ai/code/artifact/b89bd04f-c28e-4fbc-9bd9-f46c9c95aea4
Cópia estática do plano: `docs/PLANO.md`.

## O que tem aqui

| Caminho | Para quê | Quem usa |
| --- | --- | --- |
| `CLAUDE.md` | Regras e contexto que o Claude Code lê em toda sessão | Claude Code |
| `docs/PLANO.md` | Plano completo: escopo, arquitetura, segurança, roadmap | Você e o Claude Code |
| `docs/adr/` | Decisões de arquitetura | Claude Code |
| `docs/FASES.md` | Entregas, critérios de aceite e prompt de abertura de cada fase | Você |
| `docs/GLOSSARIO.md` | Termos de contratação pública usados no código | Claude Code |
| `docs/referencias/LINKS.md` | Fontes oficiais e de terceiros | Ambos |
| `scripts/baixar_referencias.ps1` | Baixa as especificações OpenAPI do PNCP e a documentação do compras-mcp | Você (uma vez) |
| `insumos/` | Modelos de planilha que **só você** pode preencher | Você |
| `.mcp.json` | Registra o compras-mcp local (stdio, versão fixada) | Claude Code |
| `.env.example`, `.gitignore` | Base de configuração segura | Claude Code |
| `src/pncp_ti/` | Snapshot diário de atas de TI, filtro de entrada e amostra | Claude Code |
| `db/migrations/` | Migrações Alembic (schema, papéis `ingest`/`mcp_reader`, views) | Claude Code |
| `scripts/backup_postgres.sh` | `pg_dump` diário do Postgres local | Você (cron no homelab) |

## Status

**Escopo (ADR 0015, 12/10/2026): só atas de registro de preços de TI vigentes.** Sem contratações, sem
contratos, sem histórico. **F0** concluída (tag `f0-fundacao`). **F1** redefinida como infraestrutura de
ingestão (motor idempotente, papéis, privacidade, backup/restore), mergeada no PR #2. O backfill
nacional foi cancelado. **F2A** (snapshot diário das atas vigentes com filtro de TI) foi mergeada no
PR #3 (`df301c3`). A migração 0004 foi aplicada após backup restaurado em banco temporário; o primeiro
snapshot nacional está em andamento e ainda não foi publicado. A F2 ainda não foi aceita: F2B (itens e
preços), rotulagem e avaliação G2 faltam. F3 está especificada, mas depende do aceite da F2 e de 20
perguntas reais revisadas em `insumos/perguntas_reais.csv`. Ver `docs/FASES.md` e `LEIA-ME-CODEX.md`.

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
com fornecedores PF. Ela permanece na cadeia histórica de migrações; a migração 0004 remove essas
tabelas no novo escopo de atas. Máscaras antigas não permitem reconstruir CPF ou desfazer fusões.
Campos/textos com sequências isoladas de 11 dígitos são mascarados conservadoramente (podem incluir
telefones/códigos); valores numéricos de preços permanecem numéricos. Erros de itens preservam os
itens válidos, mas fazem o job retornar código não zero. Logs não incluem payloads/tracebacks.

## Snapshot diário de atas de TI vigentes (ADR 0015)

O backfill nacional foi cancelado. `make ingest` consulta `/v1/atas` para a data corrente de
Brasília (`America/Sao_Paulo`), filtra objetos com sinais de TI e publica um snapshot completo somente quando todas as páginas
terminam. Uma falha mantém a última versão completa disponível. Resposta vazia no meio da
paginação e snapshot nacional sem registros são tratados como falha, preservando a carga anterior. A amostra aleatória das atas
vigentes descartadas permite revisar falsos negativos com `make amostra`.

O PNCP devolve até 50 atas por página; ~9.700 páginas têm piso teórico de 80 minutos a 2 req/s.
Latência e retries aumentam esse tempo, que ainda precisa ser medido na carga nacional. O processo registra andamento por página em `log_execucao_ingestao`. Não há
comando de backfill ou ingestão de contratos/contratações/itens nesta fase.

`v_atas_ti_vigentes` expõe ao papel `mcp_reader` apenas atas não canceladas dentro do período de
vigência. A migração 0004 substitui o schema histórico e remove os dados locais de contratações,
contratos, itens, atas antigas, fornecedores e órgãos, conforme a ADR 0015. Antes de aplicá-la a
um banco existente, gere e confira
um backup. Esta migração ainda não foi aplicada nesta sessão.

`make amostra` gera uma amostra de até 100 atas candidatas e até 100 atas vigentes rejeitadas.
O CSV registra o tamanho de cada população para que a avaliação considere a taxa de amostragem.
Textos externos que poderiam ser interpretados como fórmulas são exportados como texto literal.
O comando recusa sobrescrever o arquivo existente; use `--saida` e `--seed` para uma nova amostra.

Comandos:

```sh
make ingest
make amostra
# Se já existir um CSV, preserve-o e escolha outro nome:
uv run python -m pncp_ti.classificar.amostra --saida insumos/amostra_rotulada_atas.csv --seed 42
```

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
