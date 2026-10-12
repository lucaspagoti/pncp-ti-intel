# 0013 — Identidade de fornecedor, privacidade e sincronização de fonte mutável

- Status: aceita na correção da revisão autorizada por Lucas (12/10/2026).

## Contexto

A revisão da F1 encontrou CPF de subcontratado no JSON, CPF em logs, pessoas diferentes fundidas
pela máscara usada como PK e atualizações ignoradas por checkpoints permanentes de páginas.
Correção autorizada pelo Lucas no chat: “pode consertar”.

## Decisão

- Fornecedores têm `fornecedor_id` distinto do documento mascarado `ni`; contratos referenciam essa
  identidade e mantêm `ni_fornecedor` só para exibição. CNPJ completo público usa `cnpj:<documento>`.
- CPF completo não é persistido: calcular HMAC-SHA256 com `PNCP_TI_IDENTITY_KEY` secreta de pelo
  menos 32 bytes, mantendo a máscara de CPF para exibição. A chave só fica no `.env` e em sua cópia
  cifrada de recuperação, não no dump. Não usar hash sem chave devido ao espaço pequeno de CPFs.
- Documento incompleto/mascarado pelo upstream não comprova identidade; usar HMAC com contexto do
  contrato. Aceitamos cadastros separados para a mesma pessoa em contratos distintos nesses casos
  em vez de afirmar uma identidade que a fonte não permite estabelecer.
- Migração 0002 mantém dados legados, cria IDs aleatórios para fornecedores sem identidade segura,
  preserva vínculos CNPJ e deixa contratos PF antigos sem vínculo até reingestão. Não é possível
  recuperar CPF ou desfazer fusão antiga somente a partir da máscara.
- Mascarar fornecedor principal, subcontratado, campos novos contendo CPF e CPFs em texto livre,
  tanto em JSON quanto em colunas de texto. Conservar CNPJ e valores numéricos de preços. Sequências
  isoladas de 11 dígitos em texto são tratadas conservadoramente e podem produzir falso positivo.
- Logs de ingestão recebem só classe de erro e contexto fixo, nunca payload, mensagem externa ou
  traceback com variáveis locais. CLI retorna erro quando houver itens perdidos, preservando os bons.
- Reprocessar páginas de toda janela em nova execução. Upsert gera idempotência real; offsets de
  fonte mutável não servem como checkpoint seguro. Rotina diária também consulta atualizações de
  contratações antigas pelo cliente existente. `--forcar` permanece compatível, sem mudar essa política.
- Exigir envelope válido antes de registrar sucesso; órgãos incompletos não apagam metadados conhecidos.

## Consequências

- Backup deve incluir cópia cifrada de configuração/chave. Não rotacionar chave sem migração e
  reingestão planejadas; a rotação direta muda identidades e cria cadastros adicionais.
- Downgrade para máscara como PK é recusado quando máscaras duplicadas fariam perder identidades.
- Reprocessamento custa mais chamadas, mas não deixa offsets antigos esconderem mudanças da fonte.
  A API não oferece snapshot transacional da paginação: uma execução isolada pode observar alterações
  durante a varredura. Reexecução periódica e janelas menores reduzem esse risco; não prometemos
  fotografia consistente nem recuperação por offset.
- As views atuais não expõem `raw` nem HMAC interno. Custo diário de atas e política de reconciliação
  periódica precisam ser medidos antes de operar em volume.
