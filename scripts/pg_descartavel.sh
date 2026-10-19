#!/usr/bin/env bash
# Postgres descartável para testes e QA (ADR 0029): contêiner próprio, porta aleatória só em
# 127.0.0.1 e senhas geradas na hora. Nunca toca o banco do projeto nem o `.env` real.
#
#   scripts/pg_descartavel.sh up NOME ARQUIVO_ENV   # sobe e grava um .env sintético
#   scripts/pg_descartavel.sh down NOME             # remove o contêiner (e o volume anônimo)
#
# O ARQUIVO_ENV traz só credenciais sintéticas; carregue com `set -a; . ARQUIVO_ENV; set +a`.
set -euo pipefail

# Mesmo digest pinado em docker-compose.yml e no CI (ADR 0010); atualizar os três juntos.
IMAGEM=postgres@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d

uso() { echo 'uso: pg_descartavel.sh up NOME ARQUIVO_ENV | down NOME' >&2; exit 64; }
(( $# >= 2 )) || uso
acao=$1 nome=$2
[[ $nome =~ ^[a-z0-9][a-z0-9_.-]*$ ]] || { echo "nome inválido: $nome" >&2; exit 64; }
conteiner="pncp-ti-qa-$nome"

case $acao in
up)
    (( $# == 3 )) || uso
    arquivo=$3
    senha() { openssl rand -hex 24; }
    admin=$(senha)
    docker run -d --rm --name "$conteiner" --label pncp-ti-qa=1 \
        -e POSTGRES_DB=pncp_ti -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD="$admin" \
        -p 127.0.0.1::5432 "$IMAGEM" > /dev/null
    for _ in $(seq 60); do
        docker exec "$conteiner" pg_isready -q -U postgres -d pncp_ti -h 127.0.0.1 && break
        sleep 1
    done
    docker exec "$conteiner" pg_isready -q -U postgres -d pncp_ti -h 127.0.0.1 \
        || { echo "Postgres de QA não respondeu" >&2; docker rm -f "$conteiner" > /dev/null; exit 1; }
    porta=$(docker port "$conteiner" 5432/tcp | head -1 | sed 's/.*://')
    # Temporário 0600 e troca atômica: um destino preexistente não preserva permissão larga.
    tmp=$(mktemp "$(dirname -- "$arquivo")/.pg_descartavel.XXXXXX")
    cat > "$tmp" <<EOF
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=$porta
POSTGRES_DB=pncp_ti
POSTGRES_ADMIN_PASSWORD=$admin
PNCP_TI_INGEST_PASSWORD=$(senha)
PNCP_TI_READER_PASSWORD=$(senha)
PNCP_TI_WEB_PASSWORD=$(senha)
PNCP_TI_IDENTITY_KEY=$(openssl rand -hex 32)
EOF
    mv -f -- "$tmp" "$arquivo"
    echo "$conteiner em 127.0.0.1:$porta"
    ;;
down)
    docker rm -f -v "$conteiner" > /dev/null 2>&1 || true
    ;;
*)
    uso
    ;;
esac
