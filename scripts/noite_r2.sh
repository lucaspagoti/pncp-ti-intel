#!/usr/bin/env bash
# Supervisor de uso único da primeira carga ARP (noite de 13 para 14/10/2026, R2).
#
# 1. Garante a primeira carga ARP: tenta de novo a cada 15 min até 07:30. O checkpoint de
#    itens (data/arp/itens-*.jsonl) faz cada nova tentativa buscar só o que falta.
# 2. Roda uma segunda carga ARP para medir o modo incremental e provar que não duplica.
# 3. Atualiza o SIGA RJ.
# 4. Gera a auditoria de recall por PDM e a amostra de 10 atas (evals/arp_<data>.md).
#
# Rodar desacoplado do SSH:  setsid nohup scripts/noite_r2.sh >/dev/null 2>&1 < /dev/null &
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
exec >>logs/noite_r2.log 2>&1

INICIO=$(date -Is)
LIMITE=$(date -d "07:30" +%s)
[ "$LIMITE" -le "$(date +%s)" ] && LIMITE=$(date -d "tomorrow 07:30" +%s)
ESPERA=900

registro() { echo "[$(date '+%F %T')] $*"; }
sql() { docker compose --env-file .env exec -T postgres psql -U postgres -d pncp_ti -Atc "$1"; }
sucessos() {
    sql "SELECT count(*) FROM cargas WHERE fonte = 'compras_arp' \
         AND status IN ('concluida', 'substituida') AND iniciado_em >= '$INICIO'"
}
no_prazo() { [ "$(date +%s)" -lt "$LIMITE" ]; }
esperar_banco() {
    until sql "SELECT 1" >/dev/null 2>&1; do
        registro "Postgres indisponível; tentando subir e esperando 30 s"
        docker compose --env-file .env up -d postgres >/dev/null 2>&1
        sleep 30
        no_prazo || return 1
    done
}
rodar() {  # rodar <modulo> <rotulo>
    esperar_banco || return 1
    registro "início: $2"
    local t0=$SECONDS
    uv run python -m "$1" >>"logs/noite_r2_$2.log" 2>&1
    local status=$?
    registro "fim: $2 (status $status, $(( (SECONDS - t0) / 60 )) min)"
    grep -E '"?(arp_carga|arp_falha|siga_carga|siga_falha|auditoria_ok)' \
        "logs/noite_r2_$2.log" | tail -1 | cut -c1-900
    return $status
}

registro "supervisor iniciado; prazo $(date -d "@$LIMITE" '+%F %T')"

# Uma execução que já esteja rodando segura a trava do banco: espera ela acabar.
while pgrep -f "python -m pncp_ti.fontes.arp$" >/dev/null; do
    registro "carga ARP em andamento; aguardando"
    sleep 120
done

tentativa=0
while [ "$(sucessos)" -lt 1 ] && no_prazo; do
    tentativa=$((tentativa + 1))
    rodar pncp_ti.fontes.arp "arp_tentativa${tentativa}"
    status=$?
    [ "$status" -eq 0 ] && continue
    if [ "$status" -eq 2 ]; then
        registro "erro determinístico (dado ou contrato da API): repetir não adianta; parando"
        break
    fi
    no_prazo || break
    registro "tentativa $tentativa falhou; nova tentativa em $((ESPERA / 60)) min"
    sleep "$ESPERA"
done

if [ "$(sucessos)" -ge 1 ]; then
    registro "primeira carga ARP concluída"
    rodar pncp_ti.fontes.arp arp_incremental || registro "carga incremental falhou (a 1ª segue ativa)"
else
    registro "SEM carga ARP concluída até o prazo; ver logs/noite_r2_arp_tentativa*.log"
fi

rodar pncp_ti.fontes.siga siga || registro "carga SIGA falhou (a anterior segue ativa)"

if [ "$(sucessos)" -ge 1 ]; then
    rodar pncp_ti.fontes.arp_auditoria auditoria || registro "auditoria falhou"
fi

registro "resumo das cargas desde $INICIO:"
sql "SELECT fonte, status, to_char(iniciado_em, 'HH24:MI'), to_char(concluido_em, 'HH24:MI'), \
     coalesce(erro_tipo, ''), coalesce(contagens->>'atas_unicas', ''), \
     coalesce(contagens->>'atas_vigentes_ti', contagens->>'atas_validas_ti', '') \
     FROM cargas WHERE iniciado_em >= '$INICIO' ORDER BY iniciado_em"
registro "supervisor terminou"
