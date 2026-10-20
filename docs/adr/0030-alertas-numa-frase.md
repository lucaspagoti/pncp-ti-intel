# 0030 — Alertas no WhatsApp numa frase simples, sem repetição

- Status: aceita pelo Lucas (19/10/2026).
- Altera a ADR 0027 (o que a operação das 08:30 avisa e como) e o texto do `OnFailure`.

## Contexto

Na madrugada de 19/10/2026 o Lucas recebeu sete mensagens e não entendeu nenhuma. Duas eram
desta aplicação: a falha da carga às 04:25 (`Falha no serviço pncp-ti-carga.service; consulte
journalctl --user.`) e, às 08:32, a mesma falha dita de outro jeito (`PNCP: termo monitorado sem
carga bem-sucedida.`). As outras cinco vieram do Uptime Kuma do homelab, fora deste repositório.
Ele pediu uma frase simples, só quando houver problema, e escolheu receber uma frase toda vez
que a atualização diária falhar.

## Decisão

- O `OnFailure` manda uma frase por serviço, começando por "Atas de TI:", sem nome de unit nem
  comando. Exemplo: "Atas de TI: a atualização de hoje falhou; o site segue com os dados
  anteriores."
- A operação das 08:30 não repete o que o `OnFailure` já avisou: saem os alertas de carga que
  falhou (`{fonte}:falhou`) e de busca PNCP sem carga bem-sucedida (`pncp:indisponivel`).
- Sai também `pncp:sem_metrica`: com a ADR 0028, o termo monitorado que não respondeu no dia
  reaproveita a carga e não é incidente; se ficar 3 dias fora, a carga falha e o `OnFailure` avisa.
- Continuam: fonte sem dados, dados parados há mais de 2 dias (para a busca PNCP, contado da
  última carga bem-sucedida) e o termo estável que volta vazio. Todos os avisos do dia saem numa
  única mensagem (`alerta:<data>:resumo`).

## Consequências

- No máximo uma mensagem por falha noturna e uma por dia da verificação das 08:30.
- Uma carga manual que falhe durante o dia não gera mensagem (não tem `OnFailure`); a próxima
  carga agendada avisa se falhar de novo.
- O Uptime Kuma do homelab foi ajustado à parte (10 minutos antes de avisar e sem a mensagem de
  "voltou"), fora deste repositório.
