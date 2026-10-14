# 0021 — ARP: atas sem número PNCP, ids repetidos e listagem adaptativa

- Status: aceita (14/10/2026). Decisões do Lucas depois da primeira carga noturna da R2.
- Detalha e corrige: ADR 0020 (itens 2 e 3 e as estimativas de tempo).

## Contexto

Na noite de 13 para 14/10/2026, as 9 tentativas da primeira carga ARP falharam na conferência
do total. O déficit foi sempre o mesmo, 2.538 atas (1,7%, acima da tolerância de 1%). Uma sonda
só de leitura sobre a listagem completa achou a causa e mais dois defeitos:

1. **Cerca de 2.450 atas vêm sem `numeroControlePncpAta`** (e sem `linkAtaPNCP`). São atas
   vigentes normais, que `mapear_ata` descartava em silêncio. O endpoint de itens em lote
   (`2_consultarARPItem`), filtrado por unidade, compra e início de vigência, devolve o id
   delas, e `2.1_consultarARPItem_Id` funciona com esse id.
2. **O mesmo id aparece em mais de uma linha**: reinclusão duplicada (uma linha com
   `ataExcluido=true`, a outra não) e, raramente, duas atas diferentes com o mesmo id (erro da
   origem). O dicionário ficava com a última linha, o que podia esconder uma ata vigente.
3. **A listagem custava 3.686 requisições (41 min, 23% vazias)**, não os 10 min estimados: a
   bissecção consultava pai e filhos e começava a assinatura em 01/01/2000.

## Decisão

1. **Recuperar o id só das candidatas** (decisão do Lucas). As atas sem id com sinal de TI no
   objeto (`e_candidata`) têm o id buscado nos itens em lote, uma consulta por (unidade,
   compra, início). Só vale número com id único, que ainda não esteja na listagem. As demais
   ficam fora da base (nunca seriam TI: sem itens não há sinal de catálogo) e são contadas em
   `atas_sem_controle_pncp`. Falha na recuperação não derruba a carga (`falhas_recuperacao_id`).
2. **Conferência linha a linha.** `validar_total` exige que toda linha declarada esteja
   explicada (ata única, sem id ou descartada por data); o resto é perda e tolera 1%. Sem id
   acima de 5% das declaradas falha como mudança na API (`sem_id_excessivo`).
3. **Desempate de ids repetidos** (`arp_dados.escolher`): prefere a linha vigente na origem; no
   mesmo estado, a de `dataHoraAtualizacao` mais recente. Número de ata diferente sob o mesmo
   id conta em `atas_conflito_id` (teto de 1%).
4. **Listagem adaptativa** (decisão do Lucas, nesta rodada). Caminha pelo fim da vigência com a
   janela dimensionada pela densidade da anterior (~90% de uma página). Quando a janela estoura,
   a 1ª página serve de amostra para cortar a próxima. Num dia cheio, caminha pela assinatura
   de hoje para trás até somar o total do dia. Ficam as salvaguardas da ADR 0020: soma ≠ total
   pagina o dia, página vazia no meio é falha, fim anômalo é falha.
5. **Erros determinísticos saem com código 2** (`ERROS_DETERMINISTICOS` em `fontes/arp.py`):
   total, contrato, envelope, data anômala, catálogo, queda de volume. O supervisor da R2 para
   na hora em vez de repetir por 7 h, e o `carga_diaria.sh` registra a saída.
6. **Correções da re-revisão do Codex**: checkpoint com `formato` e versão obrigatórios; fallback
   de itens grava versão nula, para que a ata seja rebuscada no dia seguinte mesmo sem mudar;
   totais de itens precisam ser iguais em todas as páginas; a auditoria usa o mesmo filtro
   temporal da view.

## Consequências

- Recall: as atas de TI sem id na listagem voltam à base; as não candidatas sem id ficam de
  fora, visíveis na contagem.
- Atas recuperadas não têm `link_origem` (a API não traz o link).
- Os tempos medidos da listagem e da carga vão na PR #7 e no README.
