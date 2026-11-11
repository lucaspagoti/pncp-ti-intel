#!/usr/bin/env bash
# Carga diária (ADR 0017 e 0020): SIGA RJ, Compras ARP e atas PNCP, cada uma independente da outra.
# As atas PNCP vêm da API oficial de consultas (`pncp_atas`, ADR 0038); se ela falhar, a busca do
# portal (`pncp_busca`) roda na hora como reserva e publica na mesma fonte. A verificação das 08:30
# avisa quando a carga ativa veio da reserva.
# SIGA e busca PNCP que falham por instabilidade (saída 1) ganham uma nova tentativa depois de
# uma espera, se houver folga até o TimeoutStartSec=5h da unit (ADR 0037). O ARP não: leva mais
# de 2 h e repeti-lo estouraria a unit. Saída 2 é erro determinístico (dado ou contrato da
# API): precisa de gente, não de nova tentativa.
# Só avisa o Uptime Kuma (KUMA_PUSH_URL no .env, opcional) quando todas deram certo.
set -uo pipefail
cd "$(dirname "$0")/.."

ESPERA_NOVA_TENTATIVA=${PNCP_TI_ESPERA_NOVA_TENTATIVA:-1800}  # segundos
LIMITE_NOVA_TENTATIVA=${PNCP_TI_LIMITE_NOVA_TENTATIVA:-12600} # segundos de carga (3h30)
inicio=$SECONDS

rodar() {
    echo "== carga $1: $(date -Is)"
    uv run python -m "pncp_ti.fontes.$1"
}

status=0
instaveis=()
for fonte in siga arp pncp_atas; do
    rodar "$fonte"
    saida=$?
    if [ "$fonte" = pncp_atas ] && [ "$saida" -ne 0 ]; then
        echo "aviso: API oficial do PNCP falhou (saída $saida); usando a busca do portal" >&2
        fonte=pncp_busca
        rodar "$fonte"
        saida=$?
    fi
    if [ "$saida" -eq 1 ] && [ "$fonte" != arp ]; then
        echo "aviso: carga $fonte falhou (saída 1); nova tentativa no fim" >&2
        instaveis+=("$fonte")
    elif [ "$saida" -ne 0 ]; then
        echo "FALHA na carga $fonte (saída $saida)" >&2
        status=1
    fi
done

for fonte in "${instaveis[@]}"; do
    if [ $((SECONDS - inicio + ESPERA_NOVA_TENTATIVA)) -gt "$LIMITE_NOVA_TENTATIVA" ]; then
        echo "FALHA na carga $fonte (saída 1; sem tempo para nova tentativa)" >&2
        status=1
        continue
    fi
    echo "== nova tentativa de $fonte em ${ESPERA_NOVA_TENTATIVA}s"
    sleep "$ESPERA_NOVA_TENTATIVA"
    rodar "$fonte"
    saida=$?
    if [ "$saida" -ne 0 ]; then
        echo "FALHA na carga $fonte (saída $saida, depois da nova tentativa)" >&2
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
