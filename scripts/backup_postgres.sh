#!/usr/bin/env bash
# Backup diário do Postgres local (Fase 1 — base histórica).
# Uso: ./scripts/backup_postgres.sh
# Pensado para cron diário no homelab; não entra no CI.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "Falta o .env. Copie .env.example para .env e preencha antes de rodar o backup." >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-pncp_ti}"

mkdir -p backups
ARQUIVO="backups/${POSTGRES_DB}-$(date +%Y%m%dT%H%M%S).dump"

PGPASSWORD="${POSTGRES_ADMIN_PASSWORD}" pg_dump \
    --host "$POSTGRES_HOST" \
    --port "$POSTGRES_PORT" \
    --username postgres \
    --dbname "$POSTGRES_DB" \
    --format custom \
    --file "$ARQUIVO"

echo "Backup gravado em $ARQUIVO"
