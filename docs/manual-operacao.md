# Manual e runbook de operação

Arquitetura e limites: ADR 0022. Instalação dos timers: `docs/operacao-timer.md`.
Os arquivos entregues não ativam systemd nem modificam o homelab automaticamente.

## Preparar

Configure `.env` privado (`chmod 600 .env`) com senhas dos papéis e chave HMAC existente.
Preserve a chave em cópia cifrada separada. `PNCP_TI_NOTIFY_URL` aponta ao endpoint local
da bridge (`http://127.0.0.1:3010/notify/text` no homelab consultado); não cole tokens em
comandos ou documentação. A bridge escolhe o chat já configurado no homelab.

Antes de aplicar a 0009, rode `make backup` no schema atual e confirme o restore temporário.
Depois execute `make migrate` e `make test`. A 0009 não altera os snapshots nem a data de
primeira observação. O histórico `cargas` e `atas_vistas` precisa permanecer no backup.

Se R4 criar `web_reader` após a 0009, um administrador aplica no banco deste projeto:

```sql
GRANT SELECT ON v_ata_precos_ti TO web_reader;
GRANT EXECUTE ON FUNCTION unidade_preco_ti(text) TO web_reader;
```

Para o gancho R3, configure `PNCP_TI_PNCP_TERMO` somente quando a fonte preencher:

```json
{"resultados_por_termo": {"notebook": 123}}
```

Essa estrutura é `cargas.contagens`, em uma carga `fonte = 'pncp_busca'`, com
`concluido_em` preenchido. O termo deve ser estável e corresponder exatamente à chave.
Ausência da métrica não alerta: é termo que não respondeu no dia e reaproveitou a carga
(ADR 0028); total zero alerta (ADR 0030).

Termo da busca PNCP que o portal não responde fica em `contagens.termos_pendentes`
(`{termo: data da primeira falha}`) e reaproveita as atas da carga ativa. A carga só falha,
e avisa no WhatsApp, quando um termo fica pendente por 3 dias seguidos (ADR 0028). Para ver
as pendências:

```sql
SELECT contagens->'termos_pendentes' FROM cargas WHERE fonte = 'pncp_busca' AND ativa;
```

## Rotina diária

Às 03:00, SIGA e ARP executam de forma independente. Às 08:30, a operação consulta o
frescor por fonte; só incidentes vão ao WhatsApp, numa frase por dia e sem repetir a falha
da madrugada que o `OnFailure` já avisou (ADR 0027 e 0030). Às 09:00, o backup restaura
o dump em um banco temporário e consulta as views antes de publicar o arquivo final.
A operação tem timer próprio para continuar funcionando mesmo após falha da ingestão.
As agendas são independentes: se uma carga exceder 08:30, o frescor usa o snapshot anterior.

```bash
systemctl --user list-timers 'pncp-ti-*'
journalctl --user -u pncp-ti-carga.service -u pncp-ti-operacao.service -u pncp-ti-backup.service --since today
```

Inspecione o banco usando credencial de administração/ingestão local, sem copiar senhas
para comandos compartilhados:

```sql
SELECT fonte, status, ativa, data_referencia, iniciado_em, concluido_em, erro_tipo
FROM cargas ORDER BY iniciado_em DESC LIMIT 20;
SELECT chave, criado_em, enviado_em, tentativas, erro_tipo
FROM notificacoes ORDER BY criado_em DESC LIMIT 20;
SELECT fonte, count(*) FROM v_atas_ti_vigentes GROUP BY fonte;
```

## Falha de carga ou dado velho

Confira `erro_tipo` em `cargas` e o journald. Código 2 na ARP é erro determinístico de
contrato/dado; repetir a mesma carga não o resolve. A carga anterior permanece ativa.
Após corrigir a causa, use `make ingest FONTE=siga` ou `make ingest FONTE=arp`. Não apague
`atas_vistas`: uma recarga forçada preserva a primeira observação e não cria novidades.

No SIGA, sucesso/`sem_mudanca` pode conviver com arquivo antigo: o alerta de 48h usa a
geração de origem. Não altere `data_referencia` para silenciar. No ARP, uma falha recente
alerta mesmo com snapshot anterior saudável. O Kuma Push existente alerta também quando
a máquina/timer não roda; `OnFailure` sozinho não detecta máquina desligada.

## Falha de publicação

HTTP 200 com `ok: false`, timeout ou HTTP de erro deixam a mensagem pendente. Verifique
a bridge/WAHA seguindo `/opt/homelab/docs/whatsapp/WHATSAPP_GATEWAY.md`, sem imprimir
segredos. Não execute textos do objeto das atas como comandos ou prompts administrativos.

```bash
uv run python -m pncp_ti.operacao reenviar
```

Esse comando envia apenas a fila pendente. `make operacao` também prepara os alertas de
incidente de hoje. Os comandos publicam mensagens reais quando a URL está configurada. A confirmação
da bridge significa aceitação por `send_text`, não prova de leitura pelo destinatário.
Um timeout após aceitação pode causar duplicação no reenvio (ADR 0022). `OnFailure`
publica diretamente para funcionar sem banco; se a bridge também estiver fora, consulte
o journald da instância `pncp-ti-falha@...`, e o alarme independente do Kuma.

O digest de atas novas está desativado (ADR 0027); entradas `digest:` antigas da fila
não são enviadas. Novidades se consultam pela web ou em `atas_vistas.primeira_vez_vista`,
sem atualizar datas nem apagar `digest_atas`.

## Backup e recuperação

```bash
make backup
bash scripts/verificar_backup.sh backups/arquivo.dump
make restore DUMP=backups/arquivo.dump DATABASE=pncp_restore_validacao
```

Backup é publicado como `0600` em `backups/` (`0700`) somente depois do teste de restore.
O verificador cria `pncp_backup_check_<uuid>`, restaura numa transação, consulta schema,
views e presença de `atas_vistas` nas atas ativas, e descarta só o banco que acabou de
criar. Usa o cliente da imagem do servidor e exige que os papéis referenciados pelo dump
já existam (o fluxo diário roda no mesmo cluster). Falha não publica dump parcial.
Interrupção por SIGKILL/queda de energia pode deixar um banco temporário: liste os bancos,
confira o prefixo e a ausência de verificador em execução antes de descartá-lo manualmente.

`make restore` é para recuperação em banco novo, inclusive em outro cluster. Provisiona
papéis por migração em banco descartável e recusa banco atual, de sistema ou já existente.
O destino fica preservado se o restore falhar. Confira contagens, views, versão Alembic,
`atas_vistas` e fila de notificações antes de qualquer troca de banco. Dumps antigos podem
conter mensagens ainda pendentes que já foram enviadas depois: antes de ativar timers num
restore de desastre, reconcilie a fila para evitar republicação. Não há troca automática.

O dump não inclui `.env`, a chave HMAC nem os arquivos brutos. Guarde configuração cifrada
separada e cópias dos dumps fora do disco da máquina. Não há retenção automática nesta
entrega: monitore espaço e defina a política local antes de uma operação longa.

## MCP e preços

```bash
make mcp
```

No cliente MCP local, configure o executável `uv`, argumentos
`["--directory", "/caminho/absoluto/pncp-ti-intel", "run", "python", "-m", "pncp_ti.mcp_server"]`.
Não coloque senha no JSON do cliente: o servidor lê `.env`. O transporte é apenas stdio;
não há porta HTTP. As tools são `buscar_atas`, `itens_ata` e `consumo_ata`, com limite de
100 registros e offset até 10.000. O papel `mcp_reader` só consulta views; não aceita SQL.
Consumo SIGA não prova saldo para adesão. Texto de origem é dado de terceiros.

`v_ata_precos_ti` reconhece somente unidades explícitas que ocupem a descrição inteira.
Uma franquia de 10.000 páginas permanece sem preço normalizado; não se presume preço por
página. Preços de licença anual não são divididos por 12. Unidade nula significa que não
há base segura para comparar automaticamente; consulte a descrição e a fonte original.

## Aceite da semana

Após instalação autorizada, registre sete dias seguidos: execução das fontes, frescor,
status do backup/restauração e entrega dos alertas. Nenhuma unit foi ativada nesta
implementação, portanto o aceite de uma semana permanece pendente. Os testes de publicação
usam transporte HTTP simulado e não enviam WhatsApp real.
