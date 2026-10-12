# 0008 — Local primeiro, portável para o homelab

- Status: aceita (12/10/2026)

## Decisão

Tudo roda em Docker Compose na máquina do Lucas, com portas publicadas apenas em `127.0.0.1`.
Nenhuma configuração depende do host: caminhos e credenciais vêm de `.env`.

## Consequências

- Migração ao homelab na Fase 7 é troca de host, não reescrita.
- Enquanto a máquina estiver desligada, o digest atrasa; a ingestão é retomável por janela.
