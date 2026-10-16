# 0024 — Exposição da web: Caddy com autenticação na frente (D7)

- Status: **proposta (16/10/2026)**. A configuração está pronta e validada em loopback; **expor
  na internet depende da confirmação do Lucas** (DNS, Cloudflare e portas são decisões dele, e as
  regras do homelab exigem confirmação explícita para exposição pública).
- Decide a D7 da ADR 0012 e do `docs/PLANO.md`.

## Decisão (D7)

1. A web continua em `127.0.0.1:8000` e o Postgres em `127.0.0.1:5432`.
2. Na frente fica o **Caddy** (`deploy/caddy/`), em `127.0.0.1:8443` por padrão, com TLS e
   `basic_auth` (usuário único, hash bcrypt) aplicado **antes** de qualquer rota, inclusive
   `/saude`. Sem credencial: 401. O Caddy roda em container pinado por digest, `network_mode: host`,
   read-only, sem capabilities além de `NET_BIND_SERVICE`, `admin off`.
3. Duas formas de chegar de fora, a escolher pelo Lucas:
   - **A (recomendada, alinhada ao homelab):** Cloudflare Tunnel já ativo (`cloudflared.service`)
     apontando um subdomínio (ex.: `atas.myhomelablp.site`) para o Caddy ou direto para a web, com
     **Cloudflare Access** (OTP/MFA) como primeira camada. O `basic_auth` do Caddy fica como segunda.
   - **B:** Caddy com Let's Encrypt (`PNCP_TLS=<e-mail>`, `PNCP_SITE_ADDRESS=<domínio>`,
     `PNCP_BIND=0.0.0.0`) e porta 443 aberta no roteador. Mais superfície; só se não houver tunnel.
4. Autenticação de usuário único e sem rate limit de login: o uso é pessoal (ADR 0012, item 5).
   Em B, adicionar fail2ban ou bloqueio por IP antes de abrir.

## Consequências

- Nada foi exposto: o Caddy de teste escuta só em loopback e foi derrubado depois da validação.
- O checklist OWASP está em `docs/owasp-web.md`; os itens que dependem da exposição real (HSTS no
  domínio final, política do Access) ficam abertos.
