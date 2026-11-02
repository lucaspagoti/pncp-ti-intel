# Checklist OWASP Top 10 (2021) da web pncp-ti

Revisão de 16/10/2026, feita pelo Claude sobre o código da R4/R5. **Não substitui um teste de
invasão.** Status: ✅ tratado e testado · 🟡 tratado, depende da exposição real · ➖ não se aplica.

| # | Risco | Situação |
|---|---|---|
| A01 | Controle de acesso quebrado | ✅ Só leitura; `web_reader` sem acesso a tabelas (`test_web_reader_so_le_views_e_nao_escreve`); sem rotas de escrita. ✅ Duas camadas (ADR 0024, opção A): Cloudflare Access só para o e-mail do Lucas e `basic_auth` no Caddy, 401 antes de qualquer rota; outro Host na porta do tunnel dá 421 (`test_caddy_config.py`). |
| A02 | Falhas criptográficas | ✅ TLS público na borda da Cloudflare; `cloudflared` → Caddy em HTTP só em loopback; CA interna no site de teste. HSTS ligado. Senha do banco e hash do `basic_auth` só em arquivos fora do Git. |
| A03 | Injeção | ✅ SQL fixo e parametrizado, ordenação por lista fechada, `LIKE` escapado, parâmetros hostis testados. ✅ Autoescape (XSS) e CSV com fórmulas neutralizadas. |
| A04 | Design inseguro | ✅ Papel mínimo, statement_timeout, limites de página (25), de exportação (5.000), de texto (200) e de corpo (64 KB no proxy). |
| A05 | Configuração incorreta | ✅ `/docs` e OpenAPI desligados; CSP `default-src 'none'`; `TrustedHost`; Caddy `admin off`, container read-only, `bind` em loopback. Sem redirecionador na :80. `WEB_ALLOWED_HOSTS` não muda: o Caddy reescreve o Host para `127.0.0.1`. |
| A06 | Componentes vulneráveis | ✅ CI com Trivy e gitleaks; htmx vendorizado e pinado (2.0.4, sha256 no commit); imagens por digest. |
| A07 | Falhas de identificação e autenticação | ✅ Cloudflare Access (código por e-mail, só um endereço, sessão de 24 h) antes do Caddy; senha longa + bcrypt no `basic_auth`. Quem não passa no Access nem chega ao `basic_auth`. |
| A08 | Falhas de integridade | ✅ Sem desserialização de entrada; sem scripts de terceiros; o texto de fontes é dado. |
| A09 | Falhas de log e monitoramento | 🟡 Log de acesso do Caddy em stdout (com `Cf-Connecting-Ip`, sem o token do Access) e do uvicorn no journal; tentativas no painel do Access. Sem alerta de falha de login (limitação aceita, uso pessoal). |
| A10 | SSRF | ➖ A web não faz requisições a URLs fornecidas pelo usuário; `link_origem` só vira `href` se `http(s)`. |

Exposição decidida em 02/11/2026 (ADR 0024, opção A, `atas.myhomelablp.site`). Fica aberto
só o alerta de falha de login (A09).
