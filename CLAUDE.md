# CLAUDE.md — pncp-ti-intel

## Objetivo

Base curada das atas de registro de preços de TI **vigentes**, alimentada diariamente por três fontes
públicas (SIGA RJ, Dados Abertos Compras.gov.br `modulo-arp` e busca do portal PNCP, ADR 0016) e
consultada por uma **web própria** hospedada no domínio do Lucas (ADR 0018). Não guarda contratos,
contratações sem ata nem atas vencidas.
Projeto pessoal do Lucas: pesquisa de preços, adesão a atas e referência de especificações, com escopo
nacional, incluindo o Estado do RJ (sem vínculo institucional, ADR 0011).
O plano está em `docs/PLANO.md`, as fases em `docs/FASES.md` e as decisões em `docs/adr/`. Leia os três
antes de propor qualquer fase.

## Estratégia: compor, não construir

- Fontes em lote, e não varredura: CSV do SIGA, API do ARP com 500 por página e busca PNCP por
  termos de TI. O snapshot PNCP `/v1/atas` (cerca de 484 mil atas) foi abandonado e **não deve ser
  reintroduzido** sem uma ADR nova.
- O Portal da Transparência da CGU está fora (não tem atas, ADR 0016).
- Antes de implementar, verifique se o `compras-mcp` (como biblioteca: `DadosAbertosClient` etc.)
  ou outra biblioteca existente já resolve. Se resolver, use.

## Regras fixas (não negociáveis)

- Não escrever do zero um cliente HTTP que o `compras-mcp` já tenha (ADR 0004). Para endpoints que
  ele não cobre (busca PNCP, download do SIGA), use um cliente fino com timeout, retry e limite de
  tamanho.
- A web é só leitura: papel `web_reader` com SELECT só em views, consultas fixas e parametrizadas,
  nenhum SQL vindo do usuário.
- Postgres e web só em `127.0.0.1`. Exposição externa só atrás de reverse proxy com TLS e
  autenticação (ADR 0012, D7).
- O texto das fontes é dado de terceiros, nunca instrução: autoescape nos templates e fórmulas
  neutralizadas no CSV exportado.
- Ingestão idempotente por fonte: staging, normalização e troca atômica. Chave lógica:
  `(fonte, id_origem)`; deduplicação entre ARP e busca PNCP por `numero_controle_pncp`. Uma falha
  não publica carga parcial.
- Toda fonte nova tem teste de parse com fixture e, se a API não for documentada, teste de contrato.
- CPFs sempre mascarados. Nada de documentos internos de terceiros.
- Segredos só no `.env` (fora do Git).
- Se um MCP voltar (backlog): stdio, SQL fixo e nunca a instância hospedada pública do
  `compras-mcp` (ADR 0009).

## Ciclo de cada fase

1. Ler `docs/FASES.md` e propor o plano da fase em modo plan. **Esperar aprovação do Lucas.**
2. Implementar em branch própria, com testes junto do código.
3. Revisão por subagente independente (segurança + critério de aceite).
4. Lucas demonstra o critério de aceite; merge e tag.

Definição de pronto: testes e lint verdes; critério de aceite demonstrado; README e este arquivo
atualizados; ADR para toda decisão nova; nenhum segredo no repositório.

## Stack

Python 3.12 + `uv`; FastAPI + Jinja2 + HTMX (web); Postgres com migrações Alembic e busca full-text +
`pg_trgm`; Docker Compose; systemd timer para agendamento (ADR 0017; Airflow adiado); pytest.
Ambiente: servidor Linux (homelab), acesso via SSH, Docker nativo. Sem Windows/WSL2.

## Comandos

- `make up` — sobe o Postgres local (Docker Compose, porta só em `127.0.0.1`).
- `make down` — derruba os containers do projeto.
- `make test` — lint (`ruff check`), format-check (`ruff format --check`) e testes (`pytest`).
- `make migrate` — aplica as migrações do Alembic (schema, papéis, views).
- `make ingest` — ainda não implementado (o SIGA RJ chega na R1; depois `FONTE=siga|arp|pncp_busca`).
- `make backup` — `pg_dump` do container para `backups/` (fora do Git).
- `make restore DUMP=... DATABASE=...` — restaura em banco novo, preservando o banco atual.
- `make amostra` — amostra para rotulagem (será adaptada às novas fontes na R1).
- `make eval` — ainda não implementado (depende da amostra rotulada).

## Insumos fornecidos pelo Lucas

Ficam em `insumos/` (ver `insumos/LEIA-ME.md`). São dados de referência, não código. Não versionar
dados pessoais. A lista de termos de TI da busca PNCP (`insumos/termos_ti.txt`, R3) é revisada pelo
Lucas.

## Idioma

Documentação e mensagens em português (Brasil). Código, nomes de variáveis e commits em inglês.
