# CLAUDE.md — pncp-ti-intel

Leia e siga as convenções compartilhadas:

@AGENTS.md

Claude Code implementa, testa e coordena; Codex revisa independentemente: QA executor
isolado para a web (ADR 0029) e somente leitura para o resto. Apenas um worker Codex
por vez; sem outros agentes.

Para desenvolvimento autorizado, use
[ade-workflow](.claude/skills/ade-workflow/SKILL.md). A skill define revisão,
limite de correções e gates de integração. Preserve a aprovação de plano e a
autorização explícita do Lucas para integrar cada PR.

## Autoridade e skills

Este arquivo é o ponto de entrada; `AGENTS.md` define convenções e governança.
Skills são procedimentos complementares e não alteram, ignoram nem contradizem
esses dois arquivos. Em conflito, siga `CLAUDE.md` e `AGENTS.md` e informe a
incompatibilidade ao Lucas. Vale para qualquer worktree ou workspace do Orca; o
nome do workspace não confere autoridade.

Use cada skill quando a tarefa pedir, sem esperar invocação, e carregue só o necessário:

- `ade-workflow`: procedimento de desenvolvimento descrito acima.
- Superpowers: planejamento, TDD, depuração e verificação. Não cria subagentes nem
  equipes paralelas, não substitui nem duplica a revisão do Codex e não muda
  decisões de arquitetura ou de entrega.
- Caveman: modo `caveman` automático, só para a concisão da conversa. Código,
  comandos, documentação, relatórios e critérios de segurança mantêm todas as
  informações necessárias.
- UI UX Pro Max: trabalho de interface e UX, quando habilitada. Respeita FastAPI +
  Jinja2 + HTMX; framework ou dependência nova exige autorização do Lucas.
- `grilling` (Grill Me): só sob demanda, para questionar requisitos, arquitetura ou
  decisões. Não roda sozinha em tarefa simples nem refaz o planejamento.
