# pncp-ti-intel

Projeto pessoal: base de atas de registro de preços de TI **vigentes**, alimentada diariamente pelo
SIGA RJ, pelo Dados Abertos Compras.gov.br (`modulo-arp`) e pela busca do portal PNCP, e consultada
por uma web própria (ADRs 0016, 0017 e 0018).

Plano: `docs/PLANO.md`. Fases: `docs/FASES.md`. Decisões: `docs/adr/`.

## O que tem aqui

| Caminho | Para quê | Quem usa |
| --- | --- | --- |
| `CLAUDE.md` | Regras e contexto que o Claude Code lê em toda sessão | Claude Code |
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

**Mudança de arquitetura em 13/10/2026 (ADR 0016).** O snapshot nacional PNCP `/v1/atas` (F2) foi
encerrado sem aceite: cerca de 484 mil atas em páginas de 50, duas cargas fracassadas e nenhuma
publicada. O projeto passou a usar três fontes em lote e uma web própria. **R0** (replanejamento e
remoção do adaptador antigo) está em andamento na branch `refactor/fontes-atas`. **R1** (ingestão do
SIGA RJ) é a próxima. Ver `docs/FASES.md` e `LEIA-ME-CODEX.md`.

Revisão R0 e ajustes locais validados em 13/10/2026: lint, formatação e 79 testes
aprovados. Aprovação/PR/merge seguem pendentes. `make ingest` ainda não implementa
coleta e retorna erro até a R1, para não sinalizar uma carga concluída.

O banco local ainda está no schema da migração 0004, sem atas carregadas. A R1 traz a migração que
substitui essas tabelas (com backup verificado antes).

## Como rodar

```
cp .env.example .env   # preencha senhas e PNCP_TI_IDENTITY_KEY antes de usar
make up                # sobe o Postgres local
make migrate           # aplica o schema (tabelas, papéis, views)
make test              # lint + testes
```

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

## Finalidade do tratamento de dados (LGPD)

Esta base trata exclusivamente dados públicos divulgados pelo SIGA RJ, pelo Compras.gov.br e pelo
PNCP, com a finalidade de uso pessoal de pesquisa e aprendizado (pesquisa de preços, adesão a atas e
referência de especificações). CPFs são mascarados. Nenhum documento interno de terceiros é armazenado aqui.
