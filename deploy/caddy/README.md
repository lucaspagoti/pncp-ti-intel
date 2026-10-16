# Caddy na frente da web pncp-ti (ADR 0024)

Nada aqui expõe a web por conta própria: o padrão escuta só em `127.0.0.1:8443`.

```bash
cp caddy.env.example caddy.env && chmod 600 caddy.env      # preencha usuário e hash
docker run --rm caddy:2.8.4-alpine caddy hash-password --plaintext 'SENHA-LONGA'
docker compose -f deploy/caddy/compose.yml up -d
curl -sk -o /dev/null -w '%{http_code}\n' https://127.0.0.1:8443/            # 401 sem credencial
curl -sk -o /dev/null -w '%{http_code}\n' -H "Authorization: Basic $(printf '%s' "$USUARIO:$SENHA" | base64)" https://127.0.0.1:8443/   # 200
```

A web em si: `deploy/systemd/pncp-ti-web.service` (unit de usuário; instalar como a do timer em
`docs/operacao-timer.md`) ou `make web` para rodar em primeiro plano. Para o domínio, siga a
opção A ou B da ADR 0024 depois de confirmar com o Lucas.
