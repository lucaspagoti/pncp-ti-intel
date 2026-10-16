# 0026 — Curadoria assistida de TI com o Hermes

- Status: **proposta (16/10/2026)**. Nada disso foi implementado nem alterou o Hermes. Mexer no
  Hermes (skill, MCP, toolsets) é mudança no homelab e depende da confirmação do Lucas.
- Depende da ADR 0025 (parâmetros da regra em arquivo).

## Objetivo

Hoje a regra de TI é determinística e boa nos casos claros (anexo da IN 05, catálogo, corte da
ADR 0025), mas tem uma **zona de dúvida** que só um humano resolve. O Lucas quer que o Hermes
ajude nessa decisão e que, com o tempo, entenda e parametrize melhor o que é TI.

Princípio: **a regra continua sendo código e arquivo auditáveis; o Hermes sugere, o Lucas
decide, e o que o Lucas decide vira rótulo que calibra a regra.** O Hermes não muda a regra nem
os dados por conta própria.

## Desenho

**1. Três zonas.** Certeza de TI (anexo, PDM central, proporção alta), certeza de não-TI, e
**dúvida**: ata com item de TI perto do corte (por exemplo 25% a 50% dos itens), ata que só passa
por termo ambíguo da busca PNCP (telefonia, internet, digitalização, "tecnologia da informação" em
objeto de material), ata com `catalogo_incidental` de muitos itens de TI. A carga diária grava
essas atas numa **fila de curadoria** com o motivo da dúvida e um resumo curto (objeto, órgão,
itens de amostra, proporção).

**2. Dados** (migração futura, todos ligados à chave lógica `(fonte, id_origem)` e ao hash do
objeto, para sobreviver a recargas): `curadoria_fila`, `curadoria_sugestao` (veredito, confiança e
justificativa curta do modelo) e `curadoria_rotulo` (TI ou NÃO_TI, quem decidiu, quando). O rótulo
do Lucas vale **na hora** como override na view (rótulo vence regra e vence Hermes).

**3. Como o Hermes entra (reativo, sem cron).** O Hermes hoje é um agente de chat com toolsets
restritos, sem cron. Então o fluxo começa **reativo**: o Lucas pergunta no Discord ou WhatsApp
"dúvidas de TI de hoje"; o Hermes chama uma tool, lê a fila, **sugere com justificativa** e o Lucas
responde "sim" ou "não"; o Hermes grava o rótulo. Sem custo quando ninguém conversa; o modelo
atual (gpt-5.4-mini) basta para a zona de dúvida.
- **Tools MCP** no servidor stdio que já existe (`make mcp`, SQL fixo, ADR 0022): `duvidas_ti`
  (lê a fila), `exemplos_rotulados` (precedentes parecidos, para calibrar) e `registrar_rotulo`
  (a única escrita: só insere em `curadoria_rotulo`, por um papel `curador` sem outro privilégio).
- **Skill** `pncp-ti-curadoria` seguindo a `SKILLS_POLICY` (curta, sem shell, sem toolset novo).
- **Memória do Hermes**: só preferências estáveis e pequenas ("telefonia é TI; EPI com mouse pad
  não"). Os rótulos ficam no banco, não na memória (`MEMORY_POLICY`).

**4. Aprendizado.** Sem treino de modelo: (a) o Hermes usa os rótulos anteriores como precedentes
(`exemplos_rotulados`), então as sugestões melhoram conforme o Lucas decide; (b) um relatório
semanal (`curadoria/avaliar`) mede a regra contra os rótulos (precisão, recall, concordância do
Hermes) e mostra a **sensibilidade dos parâmetros** ("limiar 40% corrigiria 7 falsos negativos e
traria 1 falso positivo"); (c) o Hermes redige a **proposta de ajuste** de
`insumos/regra_ti_arp.json` ou das listas de palavras com a evidência, e a mudança entra por PR
(Claude implementa, Codex revisa, Lucas autoriza), como qualquer mudança de regra.

**5. Autonomia gradual.** Só depois de ≥ 200 rótulos e concordância ≥ 95% nos últimos 100, sem viés
por fonte, a sugestão do Hermes de alta confiança pode decidir sozinha a zona de dúvida
(`motivo_ti = hermes:…`), com amostra semanal de auditoria para o Lucas. Qualquer discordância
na auditoria derruba a autonomia de volta. É reversível: o rótulo humano sempre vence.

## Riscos e controles

- **Prompt injection:** o objeto da ata é texto de terceiro. A tool devolve o texto em campo
  rotulado, truncado e com CPF mascarado; a skill manda tratá-lo como dado; o veredito é enum; a
  única escrita é um rótulo, sem efeito fora do conjunto de calibração e do override do próprio
  item. O relatório semanal lista os rótulos gravados para o Lucas conferir.
- **Escopo do Hermes:** nenhum toolset perigoso, nenhuma escrita em arquivo, nenhum SQL livre.
- **Custo:** chamadas só em conversa, cache por hash do resumo, orçamento diário.
- **Viés de confirmação:** a auditoria semanal inclui atas fora da zona de dúvida.

## Fases e dono

| Fase | O que | Quem |
|---|---|---|
| H0 | Fila de curadoria na carga, tabelas, override na view, relatório `curadoria/avaliar` | Claude (PR, revisão do Codex) |
| H1 | Tools MCP, papel `curador`, skill | Claude (PR, revisão do Codex) |
| H2 | Registrar o MCP e ativar a skill no Hermes; teste no Discord DM antes do WhatsApp | Lucas confirma, depois eu |
| H3 | Relatório semanal e propostas de ajuste de parâmetros | Hermes + Claude |
| H4 | Autonomia gradual (critérios acima) | Decisão do Lucas |

## Decisões que ficam com o Lucas

1. Começar reativo (recomendado) ou com lote diário que já deixa as sugestões prontas.
2. Canal da revisão: Discord DM ou WhatsApp.
3. Rótulo valendo na hora como override na view (recomendado).
4. Autorizar, na fase H2, a mudança de configuração do Hermes.
