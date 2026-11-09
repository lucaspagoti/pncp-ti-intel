# 0028 — Busca PNCP reaproveita a carga ativa para termo que falhar

- Status: aceita pelo Lucas (19/10/2026). Alterada pela ADR 0037 (limite de 3 dias vira aviso;
  a carga só falha aos 14 dias).
- Altera a ADR 0023 (R3: "se ainda falhar, a carga não publica") e abre uma exceção, só para
  a busca PNCP, à regra "uma falha não publica carga parcial" (ADR 0005, `AGENTS.md`).

## Contexto

Desde 18/10/2026 a carga diária falha todo dia. O portal PNCP derruba a conexão (`ReadError`)
nos termos pesados (`material de informatica`, `equipamentos de informatica`) mesmo após 6
tentativas e 2 passadas extras. Como um único termo falho recusava a carga inteira, a busca
ficou parada na carga de 17/10 e o WhatsApp avisava duas vezes por dia. Esses termos não são
ruído: concordam 96–99% com o ARP (`evals/pncp_busca_20261017.md`) e trazem milhares de atas.
Remover os termos acabaria com o alerta, mas também com essa cobertura.

## Decisão

- Termo que ainda falha depois das passadas extras fica **pendente**, e a carga é publicada.
- Para cada termo pendente, entram de novo as atas da carga ativa da `pncp_busca` ainda
  vigentes (`fim >= hoje`) cujo objeto casa o termo (`casa_termo`, o mesmo filtro da coleta).
  Ata que já veio por outro termo só ganha o termo pendente em `motivo_ti`. Termo sem base
  anterior (nunca concluiu) entra vazio.
- `cargas.contagens.termos_pendentes` guarda `{termo: data da primeira falha}`, herdada da
  carga ativa; o termo que volta a responder sai da lista. Também ficam registrados
  `termos_reaproveitados` (termos que trouxeram atas da carga anterior) e `atas_reaproveitadas`.
- **Limite de 3 dias** (`DIAS_PENDENTE`): se um termo está pendente desde 3 dias atrás ou mais,
  a carga falha como antes (`termos_falhos`, saída 1, `OnFailure` avisa no WhatsApp). Com a
  primeira falha em D, as cargas de D, D+1 e D+2 publicam; a de D+3 falha.
- Continuam derrubando a carga: contrato alterado, `sem_atas` e queda de volume acima de 50%
  (o piso conta as atas reaproveitadas).
- `resultados_por_termo` (gancho da R6) só traz os termos que responderam no dia.
- `--validar` não consulta a carga ativa: só registra os termos falhos em log.

## Consequências

- Uma instabilidade do portal deixa de parar a busca inteira e de gerar alerta diário; o alerta
  sai só quando o mesmo termo fica fora por 3 dias seguidos.
- Por até 3 dias, as atas de um termo pendente podem estar desatualizadas (ata nova daquele
  termo não entra; a ata cancelada na origem continua como estava). As vencidas saem pelo
  filtro de vigência.
- O hash de `cargas.geracao` é calculado antes do reaproveitamento e não conta as atas
  reaproveitadas; `contagens.atas_unicas` conta.
- Sem migração: tudo cabe em `cargas.contagens` (jsonb) e `atas`.
