# Glossário

| Termo | Significado | Uso no código |
| --- | --- | --- |
| PNCP | Portal Nacional de Contratações Públicas; divulgação centralizada e obrigatória dos atos da Lei 14.133 | Fonte única de dados |
| Número de controle PNCP | Identificador único de uma contratação, contrato ou ata no PNCP | Chave natural do upsert |
| Contratação (compra) | Processo de licitação ou contratação direta publicado no PNCP | Tabela `contratacoes` |
| Item | Linha da contratação (objeto, quantidade, unidade, valor) | Tabela `itens` |
| Contrato | Instrumento assinado; só tem eficácia após divulgação no PNCP (art. 94) | Tabela `contratos` |
| ARP | Ata de Registro de Preços: compromisso para contratação futura com preços registrados | Tabela `atas` |
| Adesão ("carona") | Uso de ARP de outro órgão por órgão não participante | Consultas de atas vigentes |
| ETP | Estudo Técnico Preliminar: primeira etapa do planejamento da contratação | Anexo indexado (Fase 5) |
| TR | Termo de Referência: define objeto, requisitos, modelo de execução e de gestão | Anexo indexado (Fase 5) |
| Edital | Ato convocatório da licitação; costuma vir como ZIP com anexos | Anexo indexado (Fase 5) |
| Modalidade | Pregão, concorrência, concurso, leilão, diálogo competitivo (art. 28); código obrigatório em algumas rotas da API | Parâmetro de ingestão |
| CATMAT / CATSER | Catálogos federais de materiais e serviços | Primeira camada do filtro de TI |
| Catálogo próprio de órgão | Alguns estados/municípios usam catálogo de materiais/serviços próprio (ex: SIGA no RJ), que pode não mapear para CATMAT/CATSER | Motivo do classificador (ADR 0006) |
| Pesquisa de preços | Estimativa do valor da contratação (art. 23); federal: IN SEGES/ME 65/2021 | Tools do `compras-mcp` |
| PCA | Plano de Contratações Anual | Consultado via `compras-mcp` |
| UASG | Unidade Administrativa de Serviços Gerais (federal) | Raramente relevante fora da esfera federal |
| Esfera | F (federal), E (estadual), M (municipal), D (distrital) | Filtro de consulta |
