# 0017 — Orquestração por systemd timer; Airflow adiado

- Status: aceita (13/10/2026), decisão do Lucas ("o que for mais simples").

## Contexto

Colegas sugeriram o Airflow para baixar as fontes periodicamente. A carga desta base tem três fontes
independentes que rodam uma vez por dia, sem dependências entre elas e sem backfill. O Airflow
acrescentaria webserver, scheduler e um banco de metadados (cerca de 2 a 4 GB de RAM no homelab),
além de mais uma superfície para atualizar e proteger.

## Decisão

- A ingestão é uma CLI testável (`make ingest`, com `FONTE=siga|arp|pncp_busca` opcional).
- O agendamento é feito por um **systemd timer** no homelab. Os logs vão para o journald e
  `OnFailure=` dispara o alerta (no Hermes, na fase de operação).
- O estado de cada execução fica na tabela `cargas`, e não no orquestrador.

## Consequências

- Não sobe nenhum serviço novo, e os logs ficam no mesmo lugar dos do sistema.
- Não há UI de DAGs. O acompanhamento é feito pela tabela `cargas` e pela web (fase de operação).
- **Gatilho para reavaliar o Airflow (ou Dagster/Prefect):** mais de cerca de 5 fontes, dependência
  entre cargas, necessidade de backfill parametrizado ou alguém além do Lucas operando.
