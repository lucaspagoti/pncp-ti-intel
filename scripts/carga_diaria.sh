#!/usr/bin/env bash
# Carga diária (ADR 0017 e 0020): SIGA RJ, Compras ARP e busca PNCP, cada uma independente da outra.
# Só avisa o Uptime Kuma (KUMA_PUSH_URL no .env, opcional) quando todas deram certo.
set -uo pipefail
cd "$(dirname "$0")/.."

status=0
for fonte in siga arp pncp_busca; do
    echo "== carga $fonte: $(date -Is)"
    uv run python -m "pncp_ti.fontes.$fonte"
    saida=$?
    if [ "$saida" -ne 0 ]; then
        # 2 = erro determinístico (dado ou contrato da API): precisa de gente, não de nova tentativa.
        echo "FALHA na carga $fonte (saída $saida)" >&2
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
