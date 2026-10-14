#!/usr/bin/env bash
# Carga diária (ADR 0017 e 0020): SIGA RJ e Compras ARP, cada uma independente da outra.
# Só avisa o Uptime Kuma (KUMA_PUSH_URL no .env, opcional) quando as duas deram certo.
set -uo pipefail
cd "$(dirname "$0")/.."

status=0
for fonte in siga arp; do
    echo "== carga $fonte: $(date -Is)"
    if ! uv run python -m "pncp_ti.fontes.$fonte"; then
        echo "FALHA na carga $fonte" >&2
        status=1
    fi
done

if [ "$status" -eq 0 ] && [ -f .env ]; then
    # Lido por grep: o .env tem segredos e nunca é carregado no shell.
    url=$(grep -E '^KUMA_PUSH_URL=' .env | head -1 | cut -d= -f2- | tr -d "\"'")
    if [ -n "$url" ]; then
        curl -fsS -m 10 --retry 2 -o /dev/null "$url" || echo "aviso: ping ao Kuma falhou" >&2
    fi
fi
exit "$status"
