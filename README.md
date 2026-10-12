# pncp-ti-intel — pacote inicial

Projeto pessoal: base de inteligência de contratações públicas de TI, alimentada pelo PNCP (escopo
nacional) e consultada via MCP.
Este pacote contém só documentos e configurações de partida. Nenhum código ainda: o código nasce na Fase 0, com o Claude Code.

Plano completo (versão viva, editável): https://claude.ai/code/artifact/b89bd04f-c28e-4fbc-9bd9-f46c9c95aea4
Cópia estática do plano: `docs/PLANO.md`.

## O que tem aqui

| Caminho | Para quê | Quem usa |
| --- | --- | --- |
| `CLAUDE.md` | Regras e contexto que o Claude Code lê em toda sessão | Claude Code |
| `docs/PLANO.md` | Plano completo: escopo, arquitetura, segurança, roadmap | Você e o Claude Code |
| `docs/adr/` | As 9 decisões de arquitetura já tomadas | Claude Code |
| `docs/FASES.md` | Entregas, critérios de aceite e prompt de abertura de cada fase | Você |
| `docs/GLOSSARIO.md` | Termos de contratação pública usados no código | Claude Code |
| `docs/referencias/LINKS.md` | Fontes oficiais e de terceiros | Ambos |
| `scripts/baixar_referencias.ps1` | Baixa as especificações OpenAPI do PNCP e a documentação do compras-mcp | Você (uma vez) |
| `insumos/` | Modelos de planilha que **só você** pode preencher | Você |
| `.mcp.json` | Registra o compras-mcp local (stdio, versão fixada) | Claude Code |
| `.env.example`, `.gitignore` | Base de configuração segura | Claude Code |

## Status

**Fase 0 (Fundação) concluída.** `compras-mcp` roda localmente via stdio; `pyproject.toml` (uv), `Makefile`,
`docker-compose.yml` (Postgres só em `127.0.0.1`), CI (lint, testes, varredura de segredos) e snapshot das
tools do `compras-mcp` estão no lugar. Ver `LEIA-ME-CODEX.md` para o handoff detalhado e `docs/FASES.md`
para a Fase 1 (Reconciliação), que já pode começar.

D1 (GitHub privado pessoal) e D2 (servidor Linux via SSH, sem WSL2) resolvidas — ver `docs/adr/` e
`LEIA-ME-CODEX.md`.

## Como rodar

```
cp .env.example .env   # preencha as senhas antes de usar
make up                # sobe o Postgres local
make test               # lint + testes (inclui o compras-mcp real)
```

## Antes de abrir o Claude Code (pacote original — já feito nesta instância)

1. Descompacte esta pasta onde o projeto vai morar e rode `git init`.
2. Rode `scripts/baixar_referencias.ps1` (PowerShell) para baixar as referências oficiais para `docs/referencias/`.
3. Responda as decisões D1 e D2 (ver `docs/PLANO.md`, seção "Decisões pendentes").
4. Preencha o que der em `insumos/` — veja `insumos/LEIA-ME.md` (nada bloqueia o início das fases).
5. Abra o Claude Code na pasta e cole o prompt da Fase 0 de `docs/FASES.md`.

## Finalidade do tratamento de dados (LGPD)

Esta base trata exclusivamente dados públicos divulgados no PNCP, com a finalidade de uso pessoal de
pesquisa e aprendizado (pesquisa de preços, adesão a atas e referência de especificações). CPFs são
mascarados. Nenhum documento interno de terceiros é armazenado aqui.
