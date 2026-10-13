# Plano — Base de Inteligência de Contratações de TI (PNCP + MCP)

Cópia estática de 12/10/2026. Versão viva: https://claude.ai/code/artifact/b89bd04f-c28e-4fbc-9bd9-f46c9c95aea4
Entregas e critérios de aceite por fase: `docs/FASES.md`. Decisões: `docs/adr/`.

## Visão e escopo

É um projeto pessoal do Lucas: uma base local e curada das **atas de registro de preços de TI vigentes** no país, atualizada diariamente pelo PNCP e consultada por agentes via MCP (ADR 0015). Responde em segundos o que hoje exige horas de busca manual: que atas de TI aceitam adesão agora, quanto foi registrado por item e como os órgãos especificaram. Não guarda contratações, contratos nem histórico de atas vencidas. Para consulta pontual fora desse recorte existe o `compras-mcp` ao vivo. Serve a pesquisa e aprendizado pessoal e não está atrelado a nenhum órgão (ADR 0011).

**Estratégia: compor, não construir.** O MCP Compras.gov.br (`compras-mcp`, MIT) já entrega consulta ao vivo ao PNCP, pesquisa de preços no padrão IN 65/2021, atas para adesão e links de TR/ETP. Ele entra no dia 1, rodando localmente. O projeto constrói só o que ele não faz.

**Usos prioritários**

1. Localizar atas de registro de preços de TI vigentes para adesão.
2. Pesquisa de preços a partir dos valores registrados nos itens dessas atas.
3. Referenciar especificações, SLAs e modelos de TR/ETP das compras dessas atas.
4. Digest diário de novas atas de TI.

**Fora de escopo:** sistemas internos próprios de órgãos (ex: portais estaduais de licitação), contratos sob a Lei 8.666, estatais (Lei 13.303), geração automática de documentos licitatórios e qualquer escrita em sistemas oficiais. Nenhuma saída substitui análise humana antes de qualquer uso formal.

## O que já existe e o que construímos

| Necessidade | Já existe pronto | O que construímos |
| --- | --- | --- |
| Consultar contratações, contratos e atas ao vivo | `compras-mcp`: 11 tools PNCP e 9 de atas | Nada |
| Pesquisa de preços com descarte estatístico (IQR) | `compras-mcp`: `pesquisar_precos_para_etp` | Nada; validar aplicabilidade ao RJ (D5) |
| Atas vigentes com saldo para adesão | `compras-mcp`: tools de ata e prompt `oportunidades_carona_arp` | Nada |
| Due diligence de fornecedor e sanções | `compras-mcp`: `perfil_fornecedor_completo` | Nada (chave gratuita da Transparência) |
| Links de Edital, TR e ETP | `compras-mcp`: `pncp_contratacao_arquivos` | Download, extração de ZIP aninhado e indexação |
| Cliente da API do PNCP | `pypncp`, `pncp-cli`, cliente do `compras-mcp` | Escolher e envolver |
| Exploração da API no Claude Code | Skill do `pncp-cli` | Instalar |
| Recorte curado de atas de TI vigentes | Não | **Lacuna 1:** snapshot diário + filtro de TI (ADR 0015) |
| Preço registrado por item, comparável | Não | **Lacuna 2:** itens das atas de TI + normalização |
| Busca no texto dos anexos | Não | **Lacuna 3:** RAG híbrido (só atas de TI) |
| Aviso diário de novas atas de TI | Não | **Lacuna 4:** digest no Hermes |

Histórico além da vigência saiu do escopo de propósito (ADR 0015).

## Arquitetura

```
 Claude (chat e Claude Code)            Bot Hermes (digest)
        │ stdio        │ stdio                 │
        ▼              ▼                       ▼
 ┌─────────────┐  ┌──────────────────────────────────────┐
 │ compras-mcp │  │ pncp-ti (nosso) — só leitura, sem    │
 │ (pronto)    │  │ tools de saída de dados              │
 └──────┬──────┘  └──────────────┬───────────────────────┘
        │ ao vivo                │ SQL fixo (mcp_reader)
        │                 ┌──────▼──────────────┐
        │                 │ Postgres + pgvector │
        │                 └──▲───────────────▲──┘
        │          ┌─────────┴──────┐ ┌──────┴────────────┐
        │          │ Ingestão diária│→│ Leitor de anexos  │
        │          │ upsert+filtro  │ │ (container s/rede)│
        │          └───────┬────────┘ └───────────────────┘
        ▼                  ▼  carga diária
 ┌───────────────────────────────────────────────────────┐
 │ API e arquivos do PNCP (fonte pública única, HTTPS)    │
 └───────────────────────────────────────────────────────┘
 Servidor do Lucas (homelab): Docker Compose. Serviços internos (Postgres,
 MCPs) só em loopback. Destino final: acesso remoto só via reverse proxy
 próprio, com TLS e autenticação na frente — nunca porta interna exposta
 direto (ADR 0012; mecanismo de autenticação = decisão D7).
```

**Stack:** Python 3.12 + `uv`; FastMCP; Postgres com Alembic; Docker Compose; pytest; modelos locais (D4).

**Estrutura alvo do repositório**

```
pncp-ti-intel/
├── CLAUDE.md
├── .mcp.json
├── docker-compose.yml
├── docs/adr/
├── db/migrations/
├── src/pncp_ti/
│   ├── ingest/        # cliente envolvido, janelas, upsert, log
│   ├── classify/      # filtro de TI
│   ├── normalize/     # unidades e preços
│   ├── attachments/   # download, extração, chunking
│   └── mcp_server/    # tools do pncp-ti
├── evals/
├── insumos/
└── tests/
```

## Segurança

Riscos reais: injeção de instruções no texto dos anexos, componente de terceiro comprometido e exposição acidental de serviços.

**Transporte e rede**
- Servidores MCP via stdio (recomendação da especificação MCP para servidores locais).
- Modo HTTP do `compras-mcp` sobe em `0.0.0.0` sem autenticação: não usar assim.
- Portas só em `127.0.0.1`. Ingestão sai só para `pncp.gov.br` (ADR 0015). Leitor de anexos sem rede.
- **Exposição pública (ADR 0012, Fase "Exposição pública autenticada"):** hoje nada está exposto. Quando
  essa fase acontecer, acesso remoto só via reverse proxy próprio com TLS e autenticação na frente de
  tudo — nenhum serviço interno (Postgres, MCPs) sai de loopback diretamente. Mecanismo de autenticação é
  decisão D7, em aberto.

**Terceiros**
- `compras-mcp` com versão e hash fixados; snapshot de tools no CI (detecta envenenamento de tools e "rug pull", OWASP MCP Top 10).
- `uv.lock` com hashes, imagens por digest, varredura de vulnerabilidades no CI.

**Injeção via anexos**
- Texto de anexo é dado, nunca instrução; trechos delimitados com órgão, data e link.
- `pncp-ti` sem nenhuma tool de saída de dados.
- Extração isolada, limite de tamanho, proteção contra ZIP bomb, sem macros; trechos suspeitos marcados.

**Banco**
- Papéis `ingest` e `mcp_reader`; nenhuma tool com SQL livre; backup diário e restauração testada.

**Segredos e LGPD**
- `.env` fora do Git; varredura de segredos no pre-commit.
- Tratamento de dados públicos considera finalidade, boa-fé e interesse público (LGPD, art. 7º, §3º). CPFs mascarados. Finalidade registrada no README.
- Nenhum documento interno de terceiros nesta base.
- Log de auditoria por chamada de tool, sem dados pessoais.

## Riscos

| Risco | Efeito | Mitigação |
| --- | --- | --- |
| API do PNCP muda contrato sem versionar | Ingestão quebra em silêncio | Teste diário contra a API; `compras_healthcheck`; alerta no Hermes |
| `compras-mcp` abandonado ou alterado | Perde a camada ao vivo | Versão fixada; fork possível (MIT); snapshot |
| Filtro de TI por palavra-chave perde ata de TI (objeto genérico) | Ata fica fora da base | Palavras-chave generosas; amostra das descartadas medida na rotulagem; classificador só se D6 não for atingido |
| Snapshot diário (~80 min) falha no meio | Base do dia incompleta | Upsert idempotente; reexecutar a carga; view filtra por vigência |
| Anexos escaneados ou ZIP aninhado | Lacunas no RAG | Extração recursiva; OCR só se a eval pedir |
| Bloqueio pelo WAF | Ingestão interrompida | Limite de taxa, backoff, User-Agent, janelas |
| Máquina desligada | Digest atrasa | Ingestão retomável; já roda no homelab desde a Fase 0 |
| Exposição pública mal configurada (Fase "Exposição pública autenticada") | Acesso não autorizado a dados/consultas | Proxy com TLS + autenticação antes de qualquer porta sair de loopback; revisão OWASP MCP Top 10 antes de expor; nenhum serviço interno exposto direto |

## Decisões pendentes

- [x] **D1. Repositório:** GitHub privado pessoal. https://github.com/lucaspagoti/pncp-ti-intel (12/10/2026).
- [x] **D2. Ambiente local:** servidor Linux (homelab) via SSH, Docker nativo — sem Windows/WSL2 (12/10/2026).
- [ ] **D3. Índice vetorial:** pgvector no Postgres (recomendado) ou Qdrant.
- [ ] **D4. Modelos locais:** embeddings (RAG, F4) na GPU local (recomendado) ou via API. O classificador
  só entra se a rotulagem pedir (ADR 0015).
- [x] **D5. Norma de pesquisa de preços:** não é mais decisão bloqueante — projeto pessoal, sem processo
  formal de órgão a instruir. A tool do `compras-mcp` segue a IN SEGES/ME 65/2021 (federal); se um dia o
  resultado for usado pra alguma decisão formal, conferir a norma aplicável a esse órgão antes de usar.
- [ ] **D6. Metas do filtro de TI:** precisão e recall mínimos, definidos na fase do filtro de TI.
- [ ] **D7. Autenticação para exposição pública:** mecanismo (ex: Tailscale Funnel com auth, Cloudflare
  Access, Authelia atrás de reverse proxy, Basic Auth + TLS) — decidir na fase "Exposição pública
  autenticada" (ADR 0012).
