# CLAUDE.md — pncp-ti-intel

Leia e siga as convenções compartilhadas:

@AGENTS.md

Claude Code implementa, testa e coordena; Codex revisa independentemente pelo Orca,
somente leitura. Apenas um worker Codex por vez; sem outros agentes.

Para desenvolvimento autorizado, use
[ade-workflow](.claude/skills/ade-workflow/SKILL.md). A skill define revisão,
limite de correções e gates de integração. Preserve a aprovação de plano e a
autorização explícita do Lucas para integrar cada PR.
