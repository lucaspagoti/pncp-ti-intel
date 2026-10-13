# 0016 — Três fontes de atas vigentes: SIGA RJ, Dados Abertos ARP e busca PNCP

- Status: aceita (13/10/2026), decisão do Lucas.
- Substitui: ADR 0001 (PNCP fonte única) e ADR 0015 (snapshot diário de `/v1/atas`).
- Altera: ADR 0002 (o `compras-mcp` deixa de rodar como servidor), ADR 0003 (o MCP sai do caminho
  crítico, ver ADR 0018) e ADR 0011 (o escopo continua nacional e passa a incluir o Estado do RJ via
  SIGA).

## Contexto

A ADR 0015 previa um snapshot diário de todas as atas vigentes via PNCP `/v1/atas` (cerca de 484 mil,
50 por página, umas 9,7 mil requisições), com filtro de TI aplicado na entrada. Duas tentativas de
carga nacional falharam ou foram canceladas, e nenhuma versão foi publicada. O piloto de itens (F2B)
recebeu 404 na rota `/itens`. Colegas do Lucas sugeriram trabalhar com fontes em lote, agendadas,
tratadas em SQL e consultadas por uma interface de busca.

Fontes avaliadas por chamadas reais em 13/10/2026:

| Fonte | Achado |
|---|---|
| SIGA RJ (`compras.rj.gov.br/siga/imagens/*.CSV`) | 3 CSVs completos e regenerados todo dia por volta de 04:53: atas (13.090, das quais 1.923 `Válida`), itens com valor unitário e fornecedor, participantes com quantidade demandada × consumida. Formato `latin1`, `;`, decimal com vírgula. Essas atas **não estão no PNCP**: a busca "notebook" filtrada por RJ trouxe 22 atas, nenhuma estadual. |
| Dados Abertos Compras.gov.br, `modulo-arp` | `1_consultarARP` pagina até 500 por página, com janela de até 365 dias por início de vigência. Deu 135.304 atas em 12 meses, 271 páginas. Traz objeto, status, vigência e `linkAtaPNCP`; os itens com preço vêm de `2_consultarARPItem`. Cobre a União e os entes que usam o Compras.gov.br. |
| Busca do portal PNCP (`pncp.gov.br/api/search/`) | Busca textual com `tipos_documento=ata&status=vigente`, até 500 por página, em todas as esferas. "licença de software" trouxe 326 atas (186 municipais, 70 federais, 48 estaduais, 5 distritais); "outsourcing de impressão", 114. Não é documentada e às vezes derruba a conexão. |
| Portal da Transparência (CGU) | **Não tem conjunto de atas.** O pacote "Compras" traz contratos federais, e o volume despenca em 2026 (1,4 MB em 12/2025, 7,7 KB em 07/2026, 403 em 08 e 09/2026). "Licitações" sai até 04/2024 e dá 403 de 07/2024 em diante. A página de download fica atrás de captcha. |

## Decisão

1. **A base guarda atas de registro de preços de TI vigentes de três fontes:**
   - **SIGA RJ:** download diário dos 3 CSVs, para o Estado do RJ.
   - **Dados Abertos ARP:** atas vigentes listadas em lote (500 por página), filtro de TI e depois
     itens só das atas de TI, para a esfera federal e quem usa o Compras.gov.br.
   - **Busca PNCP:** uma consulta por termo de uma lista de TI versionada, para estados e municípios
     fora do Compras.gov.br.
2. **O snapshot `/v1/atas` sai.** Não varremos mais as cerca de 484 mil atas.
3. **O Portal da Transparência da CGU fica fora**, porque não oferece atas.
4. **Cada fonte é independente.** Cada uma tem staging próprio, troca atômica do seu snapshot e
   registro em `cargas`. A falha de uma fonte não impede que as outras publiquem.
5. **Deduplicação por `numero_controle_pncp`** entre o ARP e a busca PNCP. O ARP tem preferência
   porque traz itens. As atas do SIGA não têm esse número e não se sobrepõem às do PNCP.
6. **Classificação de TI no banco:** palavras-chave de `classificar/regra.py` mais CATMAT/CATSER
   onde houver. O SIGA é pequeno o bastante para carregar inteiro e classificar depois. No ARP, as
   atas são filtradas antes da busca de itens. Na busca PNCP, a própria lista de termos já é o filtro.
7. **Os clientes HTTP vêm do `compras-mcp`, usado como biblioteca** (o `DadosAbertosClient` já cobre
   o `modulo-arp`, ADR 0004). Para a busca PNCP e o download do SIGA, usamos um cliente fino.

## Consequências

- O escopo continua nacional e ganha o Estado do RJ, que estava invisível no PNCP.
- A carga diária passa a ser de poucos minutos: 3 arquivos, algumas centenas de páginas ARP e
  dezenas de buscas.
- A busca PNCP não é documentada e precisa de teste de contrato e alerta. A cobertura de estados e
  municípios fora do Compras.gov.br depende da qualidade da lista de termos, e o recall dessa lista
  é medido na rotulagem (D6).
- O código do adaptador `/v1/atas` (`ingest/atas.py`, `cli.py`, `mapeadores.py`, `client.py`) e os
  testes do servidor `compras-mcp` foram removidos na R0. O motor (`executar.py`, `rate_limit.py`,
  `log.py`) fica para ser generalizado na R2. As tabelas da migração 0004 saem numa migração nova
  na R1, com backup verificado antes.
- Estado anterior, para o histórico: o banco local tem a migração 0004 aplicada e nenhuma ata
  carregada. O commit `a1fc870` (retry para HTTP transitório) foi mantido porque serve à R2.
