#!/usr/bin/env bash
# Somente banco temporário criado por esta execução; nunca restaura sobre o atual.
set -euo pipefail
cd "$(dirname "$0")/.."
test "$#" -eq 1 && test -f "$1" || { echo 'Informe um dump existente.' >&2; exit 1; }
compose=(docker compose --env-file .env exec -T postgres)
temporary="pncp_backup_check_$(cat /proc/sys/kernel/random/uuid | tr -d '-')"
created=0
cleanup() {
    if [ "$created" -eq 1 ]; then
        "${compose[@]}" dropdb -U postgres --force "$temporary"
    fi
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP
"${compose[@]}" createdb -U postgres --template=template0 "$temporary"
created=1
"${compose[@]}" pg_restore -U postgres --exit-on-error --single-transaction \
    -d "$temporary" < "$1"
# As consultas também exercitam a integridade do catálogo e das views restauradas.
"${compose[@]}" psql -X -U postgres -d "$temporary" -v ON_ERROR_STOP=1 -q > /dev/null <<'SQL'
SELECT version_num FROM alembic_version;
SELECT count(*) FROM cargas;
SELECT count(*) FROM atas_vistas;
SELECT count(*) FROM v_atas_ti_vigentes;
SELECT count(*) FROM v_ata_itens_ti;
SELECT count(*) FROM v_ata_consumo_item;
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM atas a JOIN cargas c ON c.id = a.carga_id AND c.ativa
        LEFT JOIN atas_vistas v ON v.fonte = c.fonte AND v.id_origem = a.id_origem
        WHERE v.id_origem IS NULL
    ) THEN RAISE EXCEPTION 'ata ativa sem primeira_vez_vista'; END IF;
END $$;
SQL
echo 'Restauração validada em banco temporário; descarte ao sair.'
