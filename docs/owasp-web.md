# Checklist OWASP Top 10 (2021) da web pncp-ti

Revisão de 16/10/2026, feita pelo Claude sobre o código da R4/R5. **Não substitui um teste de
invasão.** Status: ✅ tratado e testado · 🟡 tratado, depende da exposição real · ➖ não se aplica.

| # | Risco | Situação |
|---|---|---|
| A01 | Controle de acesso quebrado | ✅ Só leitura; `web_reader` sem acesso a tabelas (`test_web_reader_so_le_views_e_nao_escreve`); sem rotas de escrita. 🟡 Autenticação no Caddy (usuário único), 401 antes de qualquer rota, verificado em loopback. |
| A02 | Falhas criptográficas | 🟡 TLS no Caddy (CA interna em loopback; Let's Encrypt ou Cloudflare na exposição). HSTS ligado. Senha do banco só no `.env`. |
| A03 | Injeção | ✅ SQL fixo e parametrizado, ordenação por lista fechada, `LIKE` escapado, parâmetros hostis testados. ✅ Autoescape (XSS) e CSV com fórmulas neutralizadas. |
| A04 | Design inseguro | ✅ Papel mínimo, statement_timeout, limites de página (25), de exportação (5.000), de texto (200) e de corpo (64 KB no proxy). |
| A05 | Configuração incorreta | ✅ `/docs` e OpenAPI desligados; CSP `default-src 'none'`; `TrustedHost`; Caddy `admin off`, container read-only, `bind` em loopback. 🟡 Revisar `WEB_ALLOWED_HOSTS` com o domínio final. |
| A06 | Componentes vulneráveis | ✅ CI com Trivy e gitleaks; htmx vendorizado e pinado (2.0.4, sha256 no commit); imagens por digest. |
| A07 | Falhas de identificação e autenticação | 🟡 Senha longa gerada + bcrypt. Sem bloqueio por tentativas: usar Cloudflare Access (MFA) ou fail2ban ao expor. |
| A08 | Falhas de integridade | ✅ Sem desserialização de entrada; sem scripts de terceiros; o texto de fontes é dado. |
| A09 | Falhas de log e monitoramento | 🟡 Log de acesso do Caddy em stdout e do uvicorn no journal; sem alerta de falha de login. |
| A10 | SSRF | ➖ A web não faz requisições a URLs fornecidas pelo usuário; `link_origem` só vira `href` se `http(s)`. |

Itens abertos antes de expor: confirmar a opção A ou B da ADR 0024, o domínio em
`WEB_ALLOWED_HOSTS` e o alerta de falha de login.
