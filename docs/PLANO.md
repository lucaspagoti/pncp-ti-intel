# Plano — Atas de registro de preços de TI vigentes (SIGA RJ + Compras.gov.br + PNCP)

Revisado em 13/10/2026 (ADRs 0016, 0017 e 0018). A versão viva anterior
(https://claude.ai/code/artifact/b89bd04f-c28e-4fbc-9bd9-f46c9c95aea4) descreve o desenho PNCP/MCP
antigo e ficou como histórico. Entregas e critérios de aceite estão em `docs/FASES.md`; as decisões,
em `docs/adr/`.

## Visão e escopo

É um projeto pessoal do Lucas: uma base curada das **atas de registro de preços de TI vigentes**,
atualizada diariamente a partir de três fontes públicas e consultada por uma **web própria**
hospedada no domínio dele. O objetivo é pesquisar um objeto ("outsourcing de impressão", "notebook",
"licença Microsoft") e ver, em segundos, quais atas de TI estão vigentes nas esferas federal,
estadual (incluindo o Estado do RJ) e municipal, com itens, preços registrados e link de origem.
O projeto não tem vínculo institucional (ADR 0011).

**Usos prioritários**

1. Localizar atas de TI vigentes para adesão.
2. Pesquisa de preços a partir dos valores registrados nos itens dessas atas.
3. Aviso diário de novas atas de TI.
4. (Backlog) Referência de TR/ETP pelos anexos.

**Fora de escopo:** contratos e contratações sem ata, atas vencidas e histórico, o Portal da
Transparência da CGU (não tem atas, ver ADR 0016), escrita em sistemas oficiais e geração de
documentos licitatórios. Nenhuma saída substitui a análise humana antes de um uso formal.

## Fontes (ADR 0016)

| Fonte | Cobre | Como | Volume (13/10/2026) |
|---|---|---|---|
| SIGA RJ | Estado do RJ (cobertura no PNCP a confirmar) | 3 CSVs completos, regenerados por volta de 04:53: atas, itens (valor unitário, fornecedor) e participantes (qtd demandada × consumida) | 13.090 linhas (11.662 atas únicas), 1.574 válidas únicas |
| Dados Abertos Compras.gov.br, `modulo-arp` | União e entes no Compras.gov.br | API JSON, 500 por página, janela de 365 dias; itens em `2_consultarARPItem` | ~135 mil atas/ano, ~271 páginas |
| Busca do portal PNCP | Todas as esferas (estados e municípios fora do Compras.gov.br) | `api/search` com `q=<termo TI>`, `status=vigente`, 500 por página | dezenas de consultas por dia |

## Arquitetura

```
 Navegador ─HTTPS─► Caddy (TLS + autenticação, D7) ─► web FastAPI+HTMX (127.0.0.1)
                                                         │ SELECT só em views (web_reader)
 systemd timer diário ─► make ingest ─► Postgres ◄───────┘
   ├─ SIGA RJ: 3 CSVs (pula se o sha256 não mudou)
   ├─ Dados Abertos ARP: atas vigentes → filtro TI → itens das atas TI
   └─ Busca PNCP: lista de termos TI → atas vigentes → dedupe com ARP
        cada fonte: staging → normalização → troca atômica do snapshot da fonte
```

- **Orquestração:** systemd timer + CLI (ADR 0017). O Airflow fica adiado.
- **Banco:** Postgres + Alembic. Tabelas `cargas`, `atas`, `ata_itens`, `ata_participantes`,
  `atas_vistas`; views `v_atas_ti_vigentes`, `v_ata_itens_ti`, `v_ata_consumo_item` (ADR 0019).
  Busca full-text (`portuguese` + `unaccent`) + `pg_trgm` entram na R4.
- **Web:** FastAPI + Jinja2 + HTMX, só leitura (ADR 0018).
- **Clientes HTTP:** `compras-mcp` usado como biblioteca (`DadosAbertosClient`, ADR 0004) e um
  cliente fino para a busca PNCP e o download do SIGA.

**Stack:** Python 3.12 + `uv`; FastAPI/Jinja2/HTMX; Postgres + Alembic; Docker Compose; pytest;
systemd no homelab.

**Estrutura alvo do repositório**

```
pncp-ti-intel/
├── docs/adr/ · docs/PLANO.md · docs/FASES.md
├── db/migrations/
├── src/pncp_ti/
│   ├── fontes/        # siga.py, siga_csv.py (R1); arp.py, pncp_busca.py (R2, R3)
│   ├── ingest/        # motor: retry/backoff, limite de taxa, log, troca de snapshot
│   ├── classificar/   # in05.py (regra do SIGA), amostra.py (censo), avaliar.py
│   └── web/           # FastAPI + templates
├── insumos/           # termos_ti.txt, amostra rotulada
└── tests/
```

## Segurança

**Rede e exposição**
- Postgres e web só em `127.0.0.1`. O acesso remoto passa só pelo reverse proxy com TLS e
  autenticação obrigatória (ADR 0012, D7), com revisão OWASP Top 10 antes de expor.
- A ingestão sai só para `compras.rj.gov.br`, `dadosabertos.compras.gov.br` e `pncp.gov.br`.

**Dados de terceiros**
- O texto das fontes é dado, nunca instrução. A web usa autoescape, e a exportação CSV neutraliza
  fórmulas (como já faz `classificar/amostra.py`).
- Downloads têm timeout, limite de tamanho, validação estrita do cabeçalho e conferência de sha256.

**Banco**
- Papéis `ingest` (escrita) e `web_reader` (só SELECT em views). Nenhum SQL vindo do usuário; as
  consultas são fixas e parametrizadas. Backup diário com restauração testada.

**Terceiros**
- O `compras-mcp` fica fixado com hash no `uv.lock`, usado só como biblioteca. Imagens são
  referenciadas por digest, e o CI roda varredura de vulnerabilidades e de segredos.

**Segredos e LGPD**
- `.env` fica fora do Git. Os dados tratados são públicos, para uso pessoal de pesquisa (LGPD,
  art. 7º, §3º). O CPF de fornecedor pessoa física é mascarado. Nenhum documento interno de
  terceiros entra na base.

## Riscos

| Risco | Efeito | Mitigação |
|---|---|---|
| A busca PNCP (não documentada) muda ou bloqueia | Somem as atas de estados e municípios | Teste de contrato diário, retry/backoff, taxa baixa; SIGA e ARP seguem independentes |
| SIGA muda o cabeçalho, a codificação ou trunca o arquivo | Carga errada | Validação estrita (cp1252, cabeçalho, geração dos 3 arquivos); menos de 50% das atas da carga ativa não publica (ADR 0019) |
| A lista de termos TI perde atas | Recall baixo na busca PNCP | Lista revisada pelo Lucas, amostra rotulada (D6) e referências fora dos resultados; comparação com o ARP na sobreposição |
| Dados Abertos limita a taxa | Carga ARP lenta | Fila reprocessável, limite de taxa, itens só das atas de TI |
| Exposição web mal configurada | Acesso não autorizado | D7 resolvida antes de sair de loopback, só leitura, revisão OWASP |
| Máquina desligada | Base desatualizada | `cargas` registra o frescor; alerta de dado velho |

## Decisões pendentes

- [x] **D1. Repositório:** GitHub privado pessoal (12/10/2026).
- [x] **D2. Ambiente:** servidor Linux (homelab) via SSH, Docker nativo (12/10/2026).
- [ ] **D3. Índice vetorial:** adiado até existir RAG de anexos (ADR 0018).
- [ ] **D4. Modelos locais:** só se a rotulagem pedir um classificador ou o RAG for retomado.
- [x] **D5. Norma de pesquisa de preços:** não bloqueia (projeto pessoal).
- [ ] **D6. Metas do filtro de TI:** precisão e recall mínimos, definidos com a amostra rotulada.
- [ ] **D7. Autenticação para exposição:** decidir na fase de exposição (R5).
