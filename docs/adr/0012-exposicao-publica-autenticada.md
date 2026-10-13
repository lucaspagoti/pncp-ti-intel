# 0012 — Destino final: exposição no domínio pessoal, sempre atrás de autenticação

- Status: aceita (13/10/2026)
- **Alterada pela ADR 0018 (13/10/2026):** a exposição vem logo depois da web local, e não no fim.

## Contexto

As ADRs 0008 e 0009 estabelecem a postura de segurança atual: tudo roda local (hoje, no homelab via SSH),
portas só em `127.0.0.1`, nunca usar o modo HTTP de um MCP exposto sem autenticação. Isso continua válido
para o estado atual do projeto. Mas o Lucas definiu o destino final: hospedar o sistema no seu domínio
pessoal, para acessar de fora da rede local — só ele, não um serviço público para terceiros.

## Decisão

Quando a fase "Exposição pública autenticada" (antiga "F7 · Homelab", renumerada na ADR 0011) acontecer:

1. Nenhum serviço interno (Postgres, `compras-mcp`, `pncp-ti`) é exposto diretamente — eles continuam
   só em loopback.
2. Acesso remoto só através de um reverse proxy próprio, com TLS (ex: Caddy + Let's Encrypt) e
   **autenticação obrigatória na frente de tudo**, antes de qualquer requisição chegar aos serviços
   internos.
3. O mecanismo exato de autenticação é decisão D7 (`docs/PLANO.md`), em aberto — candidatos: Tailscale
   Funnel com seu próprio controle de acesso, Cloudflare Access, Authelia atrás do proxy, ou Basic Auth
   simples sobre TLS. Decidir no momento de implementar essa fase, não agora.
4. Antes de expor qualquer coisa, revisão contra o OWASP MCP Top 10 (já previsto no `docs/PLANO.md`).
5. Isso não é "serviço público" — é acesso remoto pessoal. Não projetar para tráfego de terceiros,
   rate-limit de público desconhecido ou multiusuário; se isso mudar no futuro, é decisão nova.

## Consequências

- O modo HTTP do `compras-mcp`/`pncp-ti`, hoje proibido (ADR 0009), passa a ser permitido **só** atrás
  desse proxy autenticado — nunca em `0.0.0.0` direto, consistente com a ressalva que a ADR 0009 já
  previa.
- Superfície de ataque aumenta em relação a "tudo só em loopback" — mitigado por TLS + autenticação antes
  de qualquer coisa, e pela revisão OWASP MCP Top 10 como critério de aceite da fase.
- `docs/PLANO.md` ganha a decisão D7 e uma nota de risco correspondente.
