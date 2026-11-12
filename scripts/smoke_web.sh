#!/usr/bin/env bash
# Smoke da web em execução (rito de deploy, docs/ROADMAP-WEB.md): saúde, home, as três buscas do
# aceite da R4, cabeçalhos de segurança, detalhe de uma ata e as duas exportações CSV.
# Só lê. Uso: scripts/smoke_web.sh [URL]   (padrão: $WEB_URL ou http://127.0.0.1:8000)
set -uo pipefail

base="${1:-${WEB_URL:-http://127.0.0.1:8000}}"
limite_ms="${SMOKE_LIMITE_MS:-2000}"
falhas=0
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

ok() { printf 'ok    %s\n' "$1"; }
falha() { printf 'FALHA %s\n' "$1" >&2; falhas=$((falhas + 1)); }

# GET: grava corpo e cabeçalhos; devolve "status tempo_ms".
pegar() {
    curl -sS -m 15 -o "$tmp/corpo" -D "$tmp/cab" -w '%{http_code} %{time_total}' "$1" 2>/dev/null \
        | awk '{printf "%s %d", $1, $2 * 1000}'
}

read -r status _ <<<"$(pegar "$base/saude")"
[ "$status" = 200 ] && grep -qx ok "$tmp/corpo" && ok "saude" || falha "saude (HTTP $status)"

grep -qi "^content-security-policy: default-src 'none'" "$tmp/cab" \
    && ok "CSP" || falha "CSP ausente"

read -r status _ <<<"$(pegar "$base/")"
[ "$status" = 200 ] && grep -q 'name="q"' "$tmp/corpo" && ! grep -q 'href="/ata/' "$tmp/corpo" \
    && ok "home" || falha "home (HTTP $status)"
read -r status _ <<<"$(pegar "$base/?explorar=1")"
[ "$status" = 200 ] && grep -q 'href="/ata/' "$tmp/corpo" \
    && ok "todas as atas" || falha "todas as atas (HTTP $status)"
read -r status _ <<<"$(pegar "$base/?categoria=rede")"
[ "$status" = 200 ] && grep -q 'href="/ata/' "$tmp/corpo" \
    && ok "categoria" || falha "categoria (HTTP $status)"

detalhe=""
for termo in "outsourcing de impressão" "notebook" "licença Microsoft"; do
    q="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$termo")"
    read -r status ms <<<"$(pegar "$base/?q=$q")"
    if [ "$status" != 200 ]; then
        falha "busca '$termo' (HTTP $status)"
    elif [ "$ms" -gt "$limite_ms" ]; then
        falha "busca '$termo' levou ${ms} ms (limite ${limite_ms})"
    elif ! grep -q 'href="/ata/' "$tmp/corpo"; then
        falha "busca '$termo' sem resultados"
    else
        ok "busca '$termo' (${ms} ms)"
        [ -n "$detalhe" ] || detalhe="$(grep -o 'href="/ata/[^"]*"' "$tmp/corpo" | head -1 | cut -d'"' -f2)"
    fi
done

if [ -n "$detalhe" ]; then
    read -r status _ <<<"$(pegar "$base$detalhe")"
    [ "$status" = 200 ] && ok "detalhe $detalhe" || falha "detalhe $detalhe (HTTP $status)"
    read -r status _ <<<"$(pegar "$base$detalhe/itens.csv")"
    [ "$status" = 200 ] && head -1 "$tmp/corpo" | grep -q '^id_item,' \
        && ok "CSV de itens" || falha "CSV de itens (HTTP $status)"
fi

read -r status _ <<<"$(pegar "$base/exportar.csv?q=notebook")"
[ "$status" = 200 ] && head -1 "$tmp/corpo" | grep -q '^fonte,' \
    && ok "CSV da busca" || falha "CSV da busca (HTTP $status)"

if [ "$falhas" -gt 0 ]; then
    echo "smoke: $falhas falha(s)" >&2
    exit 1
fi
echo "smoke: tudo ok"
