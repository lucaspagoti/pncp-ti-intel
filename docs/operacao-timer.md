# Operação: carga diária (systemd timer)

A carga diária roda `scripts/carga_diaria.sh` às 03:00 (Brasília): SIGA RJ, Compras ARP e busca
PNCP, cada uma independente. A janela é a madrugada, das 03:00 às 06:00. O SIGA leva ~1 min, a
busca PNCP ~45 min e a ARP o que sobra. A varredura por PDM da ARP tem orçamento de
`ARP_VARREDURA_MINUTOS` (90 na produção), e o resto da ARP leva até ~35 min. Assim a carga
termina por volta das 05:50 (ADR 0025, item 7). Uma falha em uma fonte não impede a outra, e a carga anterior continua
visível (troca atômica, ADR 0019 e 0020). Logs no journald; estado de cada execução na tabela
`cargas`.

## Instalar (uma vez)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/pncp-ti-* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pncp-ti-carga.timer
systemctl --user enable --now pncp-ti-operacao.timer pncp-ti-backup.timer
sudo loginctl enable-linger "$USER"   # o timer roda sem sessão aberta
```

Os comandos acima são instruções para instalação pelo operador: a entrega R6 não os
executa. Antes, configure `.env`, valide backup/restauração e aplique a migração 0009.
As units usam `%h/projetos/pncp-ti-intel` e `%h/.local/bin/uv`; ajuste os arquivos copiados
se a instalação estiver em outro caminho. Para atualizar uma unit já instalada, copie-a
novamente e rode `daemon-reload`; não é necessário instalar uma segunda carga timer.

A operação roda às **08:30** e o backup às **09:00**, em `America/Sao_Paulo`, com
`Persistent=true`. Os três serviços têm `OnFailure=pncp-ti-falha@%n.service`, que envia
texto pela bridge WhatsApp sem depender do banco. A unit de falha não tem `OnFailure`
recursivo. A operação tem timer independente da carga e não deixa de rodar se ARP falhar.
Ela repete a fila pendente na próxima execução; reenvio manual está no runbook.

## Operar

```bash
systemctl --user list-timers pncp-ti-carga.timer        # próxima execução
systemctl --user start pncp-ti-carga.service            # roda agora
journalctl --user -u pncp-ti-carga.service -n 100       # logs da última execução
```

```sql
SELECT fonte, status, data_referencia, concluido_em, erro_tipo
FROM cargas ORDER BY iniciado_em DESC LIMIT 10;
```

## Alerta

Com `KUMA_PUSH_URL` no `.env` (monitor *Push* do Uptime Kuma, intervalo de 26 h), o script faz um
`curl` na URL quando as duas cargas dão certo. Sem sinal por 26 h, o Kuma marca o monitor como
fora do ar e avisa no WhatsApp. A notificação do Kuma sai pela bridge do homelab (a mesma do Backrest
e do Diun), que repassa ao WAHA; o Kuma não fala direto com o WAHA. Detalhes em
`/opt/homelab/docs`.

R6 acrescenta `PNCP_TI_NOTIFY_URL` no `.env` para a bridge existente (`POST /notify/text`,
texto puro, exige `{"ok": true}`). Sem URL, publicação falha explicitamente e conserva
a fila; não marca mensagem como entregue. Fonte sem dados, dados parados >48h e termo PNCP
zerado saem numa frase por dia, separada do Push; falha de carga só pelo `OnFailure` (ADR 0030). Instalação, recuperação, limites de entrega, configuração
do termo PNCP e MCP: [manual-operacao.md](manual-operacao.md), ADR 0022.
