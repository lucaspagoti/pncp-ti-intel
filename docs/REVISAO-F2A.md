# Revisão Codex da F2A — 12/10/2026

Revisão da implementação do Luna, solicitada por Lucas com autorização para corrigir e abrir PR.
Escopo: ADR 0015, somente atas vigentes candidatas a TI; sem backfill histórico.
PR: https://github.com/lucaspagoti/pncp-ti-intel/pull/3.

## Veredito

Aprovo o desenho e a implementação corrigida para PR. O reuso do cliente PNCP, o filtro na entrada,
o staging por snapshot e a troca transacional são coerentes com o escopo. A aprovação do código
não comprova a qualidade do filtro em produção: carga nacional, rotulagem, métricas D6/G2 e F2B
continuam pendentes. A F1 já foi mergeada (PR #2); o PR desta entrega parte de `master`.

## Achados corrigidos

1. **P1 — publicação de carga parcial.** Um 204 na segunda página era convertido em zero páginas,
   encerrando a ingestão com sucesso e apagando o snapshot anterior. Reproduzido em banco efêmero.
   Agora vazio intermediário é erro; um total reduzido não encerra a carga antes das páginas já
   anunciadas. Snapshot nacional sem registros também falha, preservando a carga anterior.
2. **P2 — recuperação após erro SQL.** Falha no INSERT da amostra deixava a transação abortada;
   a limpeza falhava com `InFailedSqlTransaction` e o lock permanecia na sessão. Reproduzido com
   CNPJ sintético maior que a coluna. Amostra e publicação agora pertencem à mesma transação;
   o tratamento faz rollback antes da limpeza, preserva a exceção original e libera o lock.
3. **P2 — CSV interpretável como fórmula.** Texto externo iniciado por `=`, `+`, `-`, `@` ou
   controles de linha é exportado como texto literal. Contagens e seed continuam numéricos e o
   objeto original não é alterado na base. A recusa de sobrescrita permanece.
4. **P2 — testes dependentes de fuso e ordem.** A fixture usava o dia do host, embora a view usasse
   Brasília; em CI UTC podia falhar entre 00h e 03h UTC. A base compartilhada também podia manter
   snapshot ativo de outro teste. Corrigidos o fuso da fixture e a limpeza entre testes, sempre no
   banco UUID descartável.

## Validação

- `TZ=UTC make test`: **103 testes aprovados**, lint e format-check aprovados; dois avisos de
  depreciação de dependências (Authlib via FastMCP).
- Regressões de publicação atômica, erro durante a troca do snapshot ativo, exclusão mútua,
  liberação de lock após falha, 204 intermediário, carga vazia, envelope inválido, retry,
  duplicatas entre páginas, reclassificação, cancelamento e vigência.
- Migração 0004 exercitada em banco efêmero populado no schema 0003. `mcp_reader` consulta a view
  e continua sem acesso ao `raw` das tabelas.
- Amostra limitada a 100 por estrato, reprodutível por seed dentro do snapshot, com contagens
  populacionais corretas; CSV existente preservado.
- Fumaça real de uma página de atas e consulta via `compras-mcp`. Sem snapshot nacional ou mudança
  no banco de desenvolvimento.

- `git diff --check` e varredura local Gitleaks aprovados.

## Limites e melhorias posteriores

- A migração 0004 é destrutiva. Backup verificado é pré-requisito da aplicação operacional; o PR
  não a aplica no desenvolvimento. A revisão 0003 permanece na cadeia porque já existia nesse banco.
- A API não oferece uma fotografia consistente entre páginas. Deduplicação e guardas de paginação
  evitam falhas conhecidas, mas mudanças na fonte durante a carga ainda podem causar omissões.
- ~80 minutos é o piso teórico para ~9.700 páginas a 2 req/s; medir a duração real com latência/retries.
- Definir retenção ou resumo para o log por página antes de operar por longo prazo.
- Dimensionar a amostra com intervalos de confiança: 100 descartadas ajudam na inspeção inicial,
  mas não demonstram recall elevado de uma classe rara. Usar os pesos dos estratos na avaliação.
