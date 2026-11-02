# 0024 — Exposição da web: Caddy com autenticação na frente (D7)

- Status: **aceita (02/11/2026)**, opção A. Foi proposta em 16/10/2026, com validação só em
  loopback.
- Decide a D7 da ADR 0012 e do `docs/PLANO.md`.

## Decisão (D7)

1. A web continua em `127.0.0.1:8000` e o Postgres em `127.0.0.1:5432`.
2. Na frente fica o **Caddy** (`deploy/caddy/`), com `basic_auth` (usuário único, hash bcrypt)
   aplicado **antes** de qualquer rota, inclusive `/saude`; sem credencial, 401.
   - O container é pinado por digest e usa `network_mode: host`.
   - É read-only, sem capabilities além de `NET_BIND_SERVICE`, com `admin off` e sem o
     redirecionador da porta 80.
3. Duas formas de chegar de fora foram avaliadas:
   - **A (escolhida pelo Lucas em 02/11/2026):** o Cloudflare Tunnel que já está ativo
     (`cloudflared.service`, gerenciado pelo painel) publica `atas.myhomelablp.site`.
     - Primeira camada: **Cloudflare Access**, com aplicação self-hosted, política Allow só para
       o e-mail do Lucas, login por código por e-mail e sessão de 24 h.
     - Segunda camada: o `basic_auth` do Caddy. O Lucas pediu as duas camadas para que um erro na
       política do Access não abra a web.
   - **B (descartada):** Caddy com Let's Encrypt e a porta 443 aberta no roteador. Tem mais
     superfície, e o tunnel já existe.
4. Autenticação de usuário único e sem rate limit de login: o uso é pessoal (ADR 0012, item 5). O
   Access limita quem recebe código e registra as tentativas no painel.

## Como o tunnel chega ao Caddy

- O TLS público termina na borda da Cloudflare. O `cloudflared` fala **HTTP** com o Caddy em
  `127.0.0.1:8444`, só em loopback, sem `noTLSVerify` nem configuração de SNI.
- O site da 8444 responde só ao Host `atas.myhomelablp.site`; qualquer outro Host recebe 421 e não
  chega à web.
- O site HTTPS de `127.0.0.1:8443` (CA interna) continua para teste local. As portas 8080 e 8081 do
  host já estão ocupadas no IP da rede local.
- O Caddy reescreve o Host para `127.0.0.1` ao chamar a web, por isso `WEB_ALLOWED_HOSTS` não muda.
- O token `Cf-Access-Jwt-Assertion` não vai para a web nem para o log. O IP real fica no log em
  `Cf-Connecting-Ip`.
- O hostname público é criado **depois** da aplicação do Access, para o domínio nunca ficar no ar
  sem ela.
- `tests/test_caddy_config.py` trava as regras: todo site só em loopback, autenticação antes do
  proxy, token fora do log e da web, `admin off`.

## Consequências

- A web tem uma entrada pública, sem nenhuma porta aberta no roteador. Para desfazer, basta apagar o
  hostname público no tunnel (`deploy/caddy/README.md`).
- O Uptime Kuma não consegue monitorar a URL externa sem um service token do Access; fica para
  depois.
- Não há alerta de falha de login. O painel do Access e o log do Caddy registram as tentativas
  (`docs/owasp-web.md`, A09).
