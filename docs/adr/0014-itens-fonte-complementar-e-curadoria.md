# 0014 — Itens como fonte complementar e curadoria preservada

- Status: **substituída pela ADR 0015** (12/10/2026). Adotada antes nas correções da F2A
  autorizadas por Lucas. O escopo passou a ser só atas vigentes de TI, com itens vindos da
  compra-mãe no PNCP. A ingestão de itens via Dados Abertos não segue. Mantida como registro
  da investigação de cobertura.

## Contexto

A F1 consulta o PNCP nacionalmente (ADRs 0001/0011). A F2A passou a consultar itens em
`dadosabertos.compras.gov.br`, usando o `DadosAbertosClient` já incluído em compras-mcp.
A presença de “PNCP_14133” no nome do endpoint não demonstra que ele replica todos os
itens de todas as plataformas que publicam no PNCP. A alegação anterior de “mesmo dado”
não tinha uma comparação por compra que a sustentasse.

O [manual oficial da API Compras.gov.br, versão 2.0, fev/2026](https://www.gov.br/compras/pt-br/acesso-a-informacao/manuais/manual-dados-abertos/manual-api-compras.pdf)
descreve os itens e seus filtros na seção 10.6 (páginas 97–102), mas não garante essa
equivalência nacional. A introdução contextualiza SIASG/Compras.gov.br; isso também não
permite afirmar que o módulo contém exclusivamente contratações federais.

## Decisão

- Manter PNCP como origem da base nacional. Dados Abertos é uma fonte complementar de
  itens, preços e catálogo; a exceção ao domínio único da ADR 0001 fica explícita.
  Transporte continua nos clientes existentes, conforme ADR 0004.
- Itens são opt-in (`--entidades itens`), fora dos jobs padrão da F1. Não liberar
  backfill completo como se fosse cobertura nacional comprovada. Um piloto delimitado
  com `--desde`/`--ate` pode formar a amostra sem carregar o histórico inteiro.
- Antes de afirmar cobertura nacional de itens, comparar por número de controle e
  número do item em compras federais, estaduais e municipais de diferentes plataformas;
  acompanhar também cobertura de preço, resultado e catálogo. Comparar inclusão com
  publicação em janelas iguais não basta. Ausência/erro de uma API não comprova exclusão.
- Se houver lacunas, o caminho previsto é obter itens por compra no PNCP, com filas,
  limites de taxa, reprocessamento e enriquecimento por Dados Abertos. Esse pipeline
  adicional não é entregue nesta correção da F2A.
- Documentos incompletos/mascarados de fornecedor são identificados no contexto de
  compra **e item**; a mesma máscara em itens diferentes não comprova a mesma pessoa.
  CPF completo com HMAC e CNPJ público mantêm as identidades existentes da F1.
- A amostra inclui chave e número de item. Usar reservoir por estrato sobre a população
  inteira, em ordem estável, seed explícita e memória limitada. Não substituir um CSV
  existente nem criar uma amostra vazia que pareça pronta para rotulagem.
- Telefonia e internet com catálogo ambíguo permanecem `INDEFINIDO`; catalogação ausente
  ou inválida (inclusive código zero) não encerra a análise como `NAO_TI`. Códigos genéricos
  positivos ainda precisam ser identificados na avaliação da qualidade do catálogo. A rotulagem alimenta a F2B;
  amostra balanceada não estima métricas populacionais sem considerar as proporções.
- Lucas excluiu correções adicionais de máscara deste pedido por considerar os dados
  públicos. Esta correção não altera a sanitização; o achado registrado na revisão
  permanece documentado, sem ser condição de aceite deste trabalho autorizado.

## Evidência de consulta e limites

Em 12/10/2026, o cliente existente retornou 10 itens no intervalo de inclusão
01–02/06/2024, incluindo o órgão `00394452000103`. Consulta somente por CNPJ sem datas
retornou `ComprasNotFoundError` inclusive para esse controle positivo. Logo, a mesma
resposta para outro CNPJ não pode ser usada como prova de ausência. Uma janela de
2023–2026 retornou `ComprasHTTPError`; consultas de itens por compra na API pública PNCP
atingiram timeout. Consultas por CNPJ com inclusão cobrindo todo 2024 também atingiram
timeout, tanto para o órgão municipal `83500603000180` (compras PNCP
`83500603000180-1-000051/2024` e `83500603000180-1-000052/2024` verificadas na
listagem de publicações) quanto para o controle positivo federal. Não foram persistidos dados nem alterado o backfill da F1.
Esses resultados tornam a comparação inconclusiva e exigem repetir o ensaio com
filtros validados e controles positivos antes de divulgar abrangência.

## Consequências

A F2A pode ser usada como piloto de curadoria da população disponível nesta fonte.
Ela não demonstra o aceite de cobertura nacional nem o portão G2 da F2B. Os rótulos
ficam preservados, os itens são identificáveis e o custo do piloto é explícito.
