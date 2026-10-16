# Operação: carga diária (systemd timer)

A carga diária roda `scripts/carga_diaria.sh` às 03:00 (Brasília): SIGA RJ e depois Compras ARP,
cada uma independente. Uma falha em uma fonte não impede a outra, e a carga anterior continua
visível (troca atômica, ADR 0019 e 0020). Logs no journald; estado de cada execução na tabela
`cargas`.

## Instalar (uma vez)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/pncp-ti-carga.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pncp-ti-carga.timer
sudo loginctl enable-linger "$USER"   # o timer roda sem sessão aberta
```

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
