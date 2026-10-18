# Piloto ADE — tests/test_exportar.py

- Base: 980a4e2ba635800c0777b88d0858e157dddf5c4b
- Snapshot revisado: `980a4e2+tests/test_exportar.py:c395ce2570eadc284466f2b54a4f8c0265411cd86d414c842f2c3f85d68ac6a7`

## Tentativa 1 — revisão supervisionada (sem parecer válido)
- Run run_2aca291c6d4b, Task task_055ac4384cfa, Dispatch ctx_1484ce5e7940.
- O Codex (`--sandbox read-only`) escreveu APPROVED no terminal, mas `check`/`worker_done`
  falharam com `runtime_unavailable`: o sandbox bloqueia `connect()` no socket Unix do Orca.
- Liberar o socket exige `network.enabled=true` (rede inteira aberta) e o modo proxy impede
  criar o socket; nenhuma opção granular aceitável no Codex 0.163.0.
- Recuperação: `worker-stop` (terminal externo, nada fechado) → `worker-abandon` (status
  `failed`/`abandoned`, sem settlement artificial) → terminal do coordenador fechado.
  Nenhum `worker-release`.

## Revisão R0 — fallback `scripts/review-exec` (aceita)
- `codex exec` somente leitura, `approval_policy=never`, `multi_agent=false`, `--ephemeral`.
- Processo com código 0, JSON válido, snapshot_id e arquivos conferem, árvore idêntica
  antes/depois. Veredito **APPROVED**, 0 achados (P0–P3).
- Analisados: tests/test_exportar.py, src/pncp_ti/web/exportar.py.
- Rodadas de correção consumidas: 0 de 2.
- Limitação: o Codex rodou só os 2 testes novos; `make test` completo depende de Postgres
  (CI cobre). O fallback em si (skill/scripts) não foi revisado pelo Codex.
