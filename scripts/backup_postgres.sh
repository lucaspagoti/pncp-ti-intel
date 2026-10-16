#!/usr/bin/env bash
# Usa o cliente da mesma imagem do servidor; .env é lido pelo Compose, nunca pelo shell.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
test -f .env || { echo 'Falta o .env.' >&2; exit 1; }
mkdir -p backups
chmod 700 backups
partial=$(mktemp backups/.backup-XXXXXXXX.partial)
trap 'rm -f -- "$partial"' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP
# Conexão local no container: evita passar a senha na linha de comando.
docker compose --env-file .env exec -T postgres sh -c \
    'exec pg_dump -U postgres -d "$POSTGRES_DB" --format=custom' > "$partial"
# Confirma que o arquivo é um dump válido antes de publicar o nome final.
docker compose --env-file .env exec -T postgres pg_restore --list < "$partial" > /dev/null
# Só publica um backup que também restaura e permite consultar o schema.
bash scripts/verificar_backup.sh "$partial"
final="backups/postgres-$(date -u +%Y%m%dT%H%M%SZ)-$(basename "$partial" .partial).dump"
mv -- "$partial" "$final"
echo "Backup gravado em $final"
