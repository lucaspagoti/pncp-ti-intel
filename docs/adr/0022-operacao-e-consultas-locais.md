# 0022 — Operação com outbox, bridge WhatsApp e consultas locais

- Status: implementada na branch R6 por solicitação do Lucas (16/10/2026);
  aceite operacional de uma semana ainda pendente.
- Detalha ADRs 0017, 0019 e 0018; mantém 0009 e 0010.

## Decisões

1. **Entrega na bridge existente.** O código local do homelab
   `/opt/homelab/scripts/whatsapp/whatsapp-hermes-bridge.py` aceita `POST /notify/text`
   com texto puro e retorna `{"ok": true}` quando `send_text` confirma. HTTP 200 com
   `ok: false` é falha. `PNCP_TI_NOTIFY_URL` fica só no `.env`. Usamos essa saída para
   WhatsApp/WAHA, sem chamar Hermes ou um modelo. Altera a previsão de Hermes em FASES;
   mantém o Kuma Push como alarme independente contra ausência total de execução.
2. **Outbox no Postgres.** Migração 0009 (seguinte à 0008): `notificacoes`
   persiste mensagens e tentativas; `digest_atas` reserva identidades no mesmo commit
   da mensagem. A trava consultiva de sessão serializa preparar e enviar. Confirmação
   positiva marca `enviado_em`; reexecução não repete mensagens confirmadas. Falha mantém
   a mensagem original, inclusive para reenvio no dia seguinte.
3. **Sem promessa de exactly-once.** A bridge não aceita chave de idempotência. Se receber
   o POST e a resposta se perder, ou houver crash antes do commit da confirmação, o reenvio
   pode duplicar a mensagem. Não há retry HTTP automático. Mensagens têm até quatro atas,
   texto sanitizado e limite de 1.000 caracteres (a bridge trunca em 1.200). Erros guardam
   apenas classe, nunca corpo HTTP, DSN ou URL.
4. **Novidade é a primeira observação**, conforme `atas_vistas`, em Brasília, e só atas
   vigentes de TI entram. O dia da primeira carga bem-sucedida por fonte é tratado como
   acervo inicial, sem digest; isso também suprime entradas posteriores nesse primeiro dia.
   `cargas` concluídas/substituídas e `atas_vistas` não devem ser apagadas. A identidade do
   envio é `pncp:<numero_controle_pncp>` quando disponível, senão `(fonte, id_origem)`.
   A preferência por ARP usa a view compartilhada; não há união por similaridade textual.
   A seleção diária exige `primeira_vez_vista = hoje`; atas de dias em que a preparação não
   rodou não entram automaticamente depois. Mensagens já preparadas continuam pendentes.
5. **Frescor separado da execução.** SIGA usa o menor `Last-Modified` dos arquivos da carga
   ativa, ou meia-noite da `data_referencia` em Brasília quando ausente. Uma execução
   `sem_mudanca` não renova esse relógio. ARP alerta na última carga falha e se a ativa
   tem mais de 48h; ausência de ativa também alerta. PNCP é gancho opcional:
   `PNCP_TI_PNCP_TERMO` seleciona a chave em `cargas.contagens.resultados_por_termo`.
   Zero, métrica ausente e carga ausente/falha/antiga têm alertas distintos. Cada condição
   gera no máximo uma mensagem preparada por dia, mantendo a fila de falhas.
6. **Agendamento independente.** Carga 03:00, operação 08:30 e backup 09:00, todos em
   Brasília e persistentes. Operação roda mesmo quando uma fonte falha. `OnFailure` em
   cada serviço aponta a uma unit que publica diretamente, sem depender do Postgres.
   Falha da própria notificação fica no journald, sem recursão de `OnFailure`.
7. **Backup só é publicado depois de restaurar.** Dump custom privado, verificação do
   catálogo, restauração transacional em banco aleatório criado vazio e consultas das
   views/registro de primeiras observações. Trap descarta somente esse banco; falha de
   limpeza também falha o backup. Nenhuma migração é aplicada ao banco operacional.
   `make restore` continua sendo o caminho manual para restauração em outro banco novo.
8. **Preço conservador.** `v_ata_precos_ti` deriva unidade e preço a partir de
   `v_ata_itens_ti`, preservando todas as colunas anteriores. Reconhece somente descrição
   integral igual a uma unidade explícita (`licença/mês`, `licença mensal`, `usuário/ano`,
   `página impressa`, com variantes de acento/plural/espaço e A3/A4/A5 para página).
   Pacotes, franquias, descrições longas e unidades ambíguas ficam com unidade/preço
   normalizado nulos. Não divide por 12, quantidade, páginas ou duração inferida. Preço
   reconhecido é o unitário original; preço inválido continua nulo. Cobertura limitada
   é deliberada enquanto as fontes não fornecerem unidade estruturada confiável.
9. **MCP próprio usando o SDK oficial já instalado.** Reutiliza `mcp.server.fastmcp`,
   declara `mcp>=1.30,<2` diretamente e mantém os hashes da árvore existente. Três tools:
   busca, itens/preços e consumo, só via stdio, SQL fixo, parâmetros escapados, limites,
   statement timeout e conexão `mcp_reader` em transação só leitura. Sem proxy OpenAPI,
   OAuthProxy, HTTP ou servidor público do `compras-mcp`. As supressões da ADR 0010 não
   mudam; nenhuma feature vulnerável do `fastmcp` 2.x é utilizada.

## Integração com as branches paralelas

R3 preenche `resultados_por_termo` (feito, ADR 0023) com o total de origem por termo; não usar o número
de atas depois de deduplicar. Até isso existir, deixar o termo vazio. R4 pode consultar
`v_ata_precos_ti`; se criar `web_reader` depois da 0009, precisa conceder SELECT nessa view
e EXECUTE em `unidade_preco_ti(text)` (runbook). Não foram alterados `fontes/pncp_busca.py`,
`web/` ou `deploy/caddy`. A 0009 e a ADR 0022 podem colidir com numeração das branches do
Claude; renumerar e ajustar `down_revision` no merge, sem editar migração já aplicada.
