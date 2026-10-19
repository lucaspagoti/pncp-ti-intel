# pncp-ti-intel

Projeto pessoal: base de atas de registro de preços de TI **vigentes**, alimentada diariamente pelo
SIGA RJ, pelo Dados Abertos Compras.gov.br (`modulo-arp`) e pela busca do portal PNCP, e consultada
por uma web própria (ADRs 0016, 0017 e 0018).

Plano: `docs/PLANO.md`. Fases: `docs/FASES.md`. Decisões: `docs/adr/`.

## O que tem aqui

| Caminho | Para quê | Quem usa |
| --- | --- | --- |
| `CLAUDE.md` | Regras e contexto que o Claude Code lê em toda sessão | Claude Code |
| `.claude/settings.json`, `.caveman.json` | Plugins do projeto (Superpowers, Caveman, UI UX Pro Max) e modo padrão do Caveman | Claude Code |
| `docs/PLANO.md` | Escopo, fontes, arquitetura, segurança, riscos | Você e o Claude Code |
| `docs/adr/` | Decisões de arquitetura | Claude Code |
| `docs/FASES.md` | Entregas, critérios de aceite e prompt de abertura de cada fase | Você |
| `docs/GLOSSARIO.md` | Termos de contratação pública usados no código | Claude Code |
| `docs/referencias/LINKS.md` | Fontes oficiais e de terceiros | Ambos |
| `insumos/` | Arquivos que **só você** pode preencher (rotulagem, termos de TI) | Você |
| `.env.example`, `.gitignore` | Base de configuração segura | Claude Code |
| `src/pncp_ti/` | Motor de ingestão, regra de TI, amostra, privacidade | Claude Code |
| `db/migrations/` | Migrações Alembic (schema, papéis, views) | Claude Code |
| `scripts/backup_postgres.sh` | `pg_dump` diário do Postgres local | Você (agendado no homelab) |

## Status

**Arquitetura (ADR 0016):** três fontes em lote de atas de registro de preços de TI vigentes (SIGA RJ,
Compras.gov.br ARP e, na R3, busca PNCP) e uma web própria. O snapshot nacional PNCP `/v1/atas`
foi abandonado em 13/10/2026.

- **R1 — SIGA RJ** (ADR 0019): 11.663 atas, 52.014 itens e 138.255 participantes; 24 atas de TI
  vigentes em 14/10/2026 (critério: Anexo Único da IN PRODERJ 05/2024). Precisão e recall de 100%
  sobre o censo rotulado pelo anexo (ressalvas em `evals/siga_20261013.md`).
- **R2 — Compras.gov.br ARP** (ADR 0020 e 0021): 1ª carga real em 14/10/2026, com 146.134 atas
  vigentes listadas (148.575 declaradas pela API; 2.515 vêm sem identificador do PNCP), **6.161
  atas de TI vigentes** e 22.636 itens com preço. Critério de TI: anexo da IN 05 ou catálogo
  (CATMAT grupo 70 / CATSER). Conferência de 10 atas contra o PNCP: 10/10. Recall por PDM de TI:
  59% (atas com objeto genérico escapam; ver `evals/arp_20261014.md`).
- **Carga diária** às 03:00 por systemd timer (`scripts/carga_diaria.sh`, `docs/operacao-timer.md`):
  SIGA e depois ARP. A ARP é incremental (reaproveita os itens das atas sem mudança).
- **R6 — Operação preparada para instalação** (ADR 0022): `OnFailure`, timer diário de
  backup com restore temporário antes de publicar, alertas de incidente no WhatsApp
  pela bridge existente (sem digest de atas, ADR 0027). Fila persistente para reenvio e preservação de `primeira_vez_vista`.
  Units entregues sem ativação; uma semana sem intervenção ainda precisa ser demonstrada.
- **Backlog implementado:** view `v_ata_precos_ti` com unidades explícitas conservadoras,
  MCP próprio stdio (`make mcp`) com consultas fixas e papel `mcp_reader`, e
  [manual/runbook](docs/manual-operacao.md). Migração nova: **0009**, após a 0008;
  coordenar numeração com as branches paralelas R3/R4 do Claude antes de integrar.

`make ingest FONTE=siga|arp|pncp_busca` roda uma carga manualmente e `make web` sobe a web local
(`127.0.0.1:8000`; proxy autenticado em `deploy/caddy/`, ADR 0024). O banco local está na migração 0008.

## Como rodar

```
cp .env.example .env   # preencha senhas e PNCP_TI_IDENTITY_KEY antes de usar
make up                # sobe o Postgres local
make migrate           # aplica o schema (tabelas, papéis, views)
make test              # lint + testes
make e2e               # E2E da web no Chromium (Playwright)
```

O E2E precisa do Chromium do Playwright (`uv run playwright install chromium`). No homelab,
sem sudo, `make e2e` usa as bibliotecas extraídas por `scripts/playwright_libs.sh`. Para testar
sem o `.env` real: `scripts/pg_descartavel.sh up dev /caminho/qa.env`, carregar esse arquivo no
ambiente e rodar `make migrate test e2e`; `scripts/pg_descartavel.sh down dev` remove.

## Identidade e privacidade

Gere `PNCP_TI_IDENTITY_KEY` com `python -c "import secrets; print(secrets.token_hex(32))"`
e copie o resultado para `.env` (permissão `0600`). CPF completo só é usado em memória para gerar
HMAC-SHA256; máscara e identidade são campos separados. Identificadores já mascarados na origem
ficam isolados por contrato, pois não comprovam identidade global. CNPJ público permanece íntegro.
Guarde a chave com o backup cifrado de configuração; alterá-la requer plano de migração/reingestão.

A migração `0002` preservou registros legados, limpa CPF dos textos/JSON e remove vínculos ambíguos
com fornecedores PF. Ela permanece na cadeia histórica de migrações; a migração 0004 remove essas
tabelas no novo escopo de atas. Máscaras antigas não permitem reconstruir CPF ou desfazer fusões.
Campos/textos com sequências isoladas de 11 dígitos são mascarados conservadoramente (podem incluir
telefones/códigos); valores numéricos de preços permanecem numéricos. Erros de itens preservam os
itens válidos, mas fazem o job retornar código não zero. Logs não incluem payloads/tracebacks.

## Backup diário e restauração segura

O backup usa `pg_dump` dentro do container Postgres (mesma versão do servidor), valida o
arquivo, restaura em banco temporário e consulta as views antes de publicar o nome final
por rename atômico. Arquivos têm permissão `0600`; falhas
removem somente o arquivo parcial. O `.env` nunca é executado pelo shell.

Agendamento entregue por systemd: backup às 09:00 e operação às 08:30, em Brasília.
Instalação manual em [docs/operacao-timer.md](docs/operacao-timer.md). Se havia cron de backup,
substitua-o pelo timer para evitar duplicidade. Defina retenção e cópia externa conforme o
espaço disponível; a entrega não altera os agendamentos reais.

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

Para os alertas de incidente, configure `PNCP_TI_NOTIFY_URL` no `.env` com a bridge local `/notify/text`.
`make operacao` prepara e publica; `uv run python -m pncp_ti.operacao reenviar` tenta apenas
pendências (digests antigos nunca são enviados). O gancho
`PNCP_TI_PNCP_TERMO` fica vazio até a R3 preencher `contagens.resultados_por_termo`.
Limites de reenvio, recuperação e uso do MCP estão no manual. Anexos/RAG, outros sistemas
estaduais e renomeação continuam pendentes de decisão do Lucas.

## Finalidade do tratamento de dados (LGPD)

Esta base trata exclusivamente dados públicos divulgados pelo SIGA RJ, pelo Compras.gov.br e pelo
PNCP, com a finalidade de uso pessoal de pesquisa e aprendizado (pesquisa de preços, adesão a atas e
referência de especificações). CPFs são mascarados. Nenhum documento interno de terceiros é armazenado aqui.
