# Caddy na frente da web pncp-ti (ADR 0024)

A web fica publicada em `https://atas.myhomelablp.site`, pela opção A da ADR 0024: Cloudflare Tunnel,
com o Cloudflare Access e o `basic_auth` deste Caddy na frente.

```
navegador ─TLS─> Cloudflare (Access: código por e-mail, só o Lucas) ─tunnel─> cloudflared (host)
   └─> http://127.0.0.1:8444  Caddy (basic_auth, headers, 64 KB)  ─> 127.0.0.1:8000 web
```

O Caddy escuta só em loopback:

- `127.0.0.1:8443`: HTTPS com a CA interna, para teste local;
- `127.0.0.1:8444`: HTTP, a entrada do `cloudflared`. Responde só ao Host `atas.myhomelablp.site`;
  qualquer outro Host recebe 421.

O redirecionador da porta 80 está desligado. O token do Access (`Cf-Access-Jwt-Assertion`) não chega
à web e não vai para o log. O IP real do visitante aparece no log em `Cf-Connecting-Ip`.

## Subir o Caddy

```bash
cp caddy.env.example caddy.env && chmod 600 caddy.env      # preencha usuário e hash
docker run --rm -it caddy:2.8.4-alpine caddy hash-password  # pede a senha; cole o hash no caddy.env
docker compose -f deploy/caddy/compose.yml up -d
ss -ltn | grep -E ':844[34] '                               # as duas portas só em 127.0.0.1
```

Conferir a entrada do tunnel em loopback:

```bash
H='Host: atas.myhomelablp.site'
curl -s -o /dev/null -w '%{http_code}\n' -H "$H" http://127.0.0.1:8444/          # 401
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: outro' http://127.0.0.1:8444/  # 421
curl -s -o /dev/null -w '%{http_code}\n' -H "$H" -H "Authorization: Basic $(printf '%s' "$USUARIO:$SENHA" | base64)" http://127.0.0.1:8444/saude   # 200
```

O `restart: unless-stopped` do compose religa o Caddy no boot. A web em si é a unit
`deploy/systemd/pncp-ti-web.service`; para teste, `make web`.

## Cloudflare Zero Trust (uma vez, nesta ordem)

1. **Access → Applications → Add → Self-hosted:**
   - domínio `atas.myhomelablp.site`;
   - política **Allow**, com Include → Emails = o e-mail do Lucas;
   - login por **One-time PIN**;
   - sessão de 24 h.

   O Access vem antes do hostname para o domínio nunca ficar no ar sem ele.
2. **Networks → Tunnels → tunnel do homelab → Public hostname → Add:** subdomínio `atas`, domínio
   `myhomelablp.site`, serviço **HTTP** `127.0.0.1:8444`. A Cloudflare cria o CNAME.

## Verificar de fora (rede do celular)

- `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://atas.myhomelablp.site/saude`
  deve dar 302 para `*.cloudflareaccess.com`, e o `docker logs pncp_ti_caddy` não ganha linha.
- No navegador: código do Access por e-mail, depois o `basic_auth` (senha errada dá 401) e a busca.

## Desfazer

1. Apagar o *Public hostname* `atas` no tunnel; o domínio sai do ar na hora.
2. Se quiser, `docker compose -f deploy/caddy/compose.yml down`.
3. Se quiser, remover a aplicação do Access.

A web continua em `127.0.0.1:8000`.
