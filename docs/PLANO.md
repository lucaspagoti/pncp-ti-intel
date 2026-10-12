# Plano — Base de Inteligência de Contratações de TI (PNCP + MCP)

Cópia estática de 12/10/2026. Versão viva: https://claude.ai/code/artifact/b89bd04f-c28e-4fbc-9bd9-f46c9c95aea4
Entregas e critérios de aceite por fase: `docs/FASES.md`. Decisões: `docs/adr/`.

## Visão e escopo

O produto é uma base local e curada de contratações públicas de TI, alimentada diariamente pelo PNCP e consultada por agentes via MCP. Responde em segundos o que hoje exige horas de busca manual: que atas vigentes aceitam adesão, quanto outros órgãos pagaram por um item e como especificaram contratações parecidas.

**Estratégia: compor, não construir.** O MCP Compras.gov.br (`compras-mcp`, MIT) já entrega consulta ao vivo ao PNCP, pesquisa de preços no padrão IN 65/2021, atas para adesão e links de TR/ETP. Ele entra no dia 1, rodando localmente. O projeto constrói só o que ele não faz.

**Usos prioritários na GTI/PGE-RJ**

1. Pesquisa de preços para ETP e TR (contratações similares de até 1 ano, art. 23, §1º, II da Lei 14.133).
2. Localizar atas de registro de preços vigentes para adesão.
3. Referenciar especificações, SLAs e modelos de TR/ETP de outros órgãos.
4. Digest diário de novas contratações de TI.

**Fora de escopo:** SIGA-RJ, contratos sob a Lei 8.666, estatais (Lei 13.303), geração automática de documentos licitatórios e qualquer escrita em sistemas oficiais. Nenhuma saída substitui a análise do servidor responsável.

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
| Histórico além de 365 dias | Não | **Lacuna 1:** banco local persistente |
| Recorte curado de TI | Não | **Lacuna 2:** filtro por catálogo + classificador |
| Preço por unidade comparável | Não | **Lacuna 3:** normalização |
| Busca no texto dos anexos | Não | **Lacuna 4:** RAG híbrido |
| Aviso diário de novas contratações | Não | **Lacuna 5:** digest no Hermes |

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
 Máquina do Lucas: Docker Compose, portas só em 127.0.0.1
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
- Portas só em `127.0.0.1`. Ingestão só sai para `pncp.gov.br`. Leitor de anexos sem rede.

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
- Nenhum documento interno da PGE nesta base.
- Log de auditoria por chamada de tool, sem dados pessoais.

## Riscos

| Risco | Efeito | Mitigação |
| --- | --- | --- |
| API do PNCP muda contrato sem versionar | Ingestão quebra em silêncio | Teste diário contra a API; `compras_healthcheck`; alerta no Hermes |
| `compras-mcp` abandonado ou alterado | Perde a camada ao vivo | Versão fixada; fork possível (MIT); snapshot |
| Cobertura do RJ no PNCP incompleta | Base enviesada | Reconciliação na Fase 1 (G1) |
| Catálogo próprio do RJ derruba o filtro | TI fica de fora | Classificador + amostra rotulada |
| Anexos escaneados ou ZIP aninhado | Lacunas no RAG | Extração recursiva; OCR só se a eval pedir |
| Bloqueio pelo WAF | Ingestão interrompida | Limite de taxa, backoff, User-Agent, janelas |
| Máquina desligada | Digest atrasa | Ingestão retomável; homelab na Fase 7 |

## Decisões pendentes

- [x] **D1. Repositório:** GitHub privado pessoal. https://github.com/lucaspagoti/pncp-ti-intel (12/10/2026).
- [x] **D2. Ambiente local:** servidor Linux (homelab) via SSH, Docker nativo — sem Windows/WSL2 (12/10/2026).
- [ ] **D3. Índice vetorial:** pgvector no Postgres (recomendado) ou Qdrant.
- [ ] **D4. Modelos locais:** classificador e embeddings na GPU local (recomendado) ou via API.
- [ ] **D5. Norma de pesquisa de preços:** a tool do `compras-mcp` segue a IN SEGES/ME 65/2021 (federal); confirmar o regulamento estadual aplicável ao RJ.
- [ ] **D6. Metas do filtro de TI:** precisão e recall mínimos, definidos na Fase 3.
