.PHONY: up down test migrate ingest backup restore amostra eval

up: ## Sobe o Postgres local (porta só em 127.0.0.1).
	@test -f .env || (echo "Falta o .env. Copie .env.example para .env e preencha antes de rodar 'make up'." && exit 1)
	docker compose --env-file .env up -d
	@echo "Aguardando Postgres ficar saudável..."
	@timeout 60 bash -c 'until docker compose --env-file .env ps postgres | grep -q "(healthy)"; do sleep 1; done'
	@echo "Postgres pronto em 127.0.0.1:$${POSTGRES_PORT:-5432}."

down: ## Derruba os containers do projeto.
	docker compose down

test: ## Lint + format-check + testes.
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

migrate: ## Aplica as migrações do Alembic (schema, papéis, views).
	uv run alembic upgrade head

FONTE ?= siga

ingest: ## Carga de uma fonte: make ingest FONTE=siga|arp [ARGS=--validar] (pncp_busca: R3).
	@case "$(FONTE)" in siga|arp) ;; *) echo "FONTE=$(FONTE) ainda não implementada (pncp_busca: R3)." >&2; exit 1;; esac
	uv run python -m pncp_ti.fontes.$(FONTE) $(ARGS)

backup: ## pg_dump do Postgres local para backups/ (fora do Git).
	./scripts/backup_postgres.sh

restore: ## Restaura em banco NOVO: make restore DUMP=backups/arquivo.dump DATABASE=nome_novo
	@test -n "$(DUMP)" -a -n "$(DATABASE)" || (echo "Informe DUMP e DATABASE." && exit 1)
	./scripts/restore_postgres.sh "$(DUMP)" --database "$(DATABASE)"

amostra: ## Exporta insumos/rotulagem_siga.csv (censo das atas vigentes) para rotular TI.
	uv run python -m pncp_ti.classificar.amostra

eval: ## Precisão/recall do filtro de TI: make eval ROT=insumos/rotulagem_siga.csv
	@test -n "$(ROT)" || (echo "Informe ROT=<csv rotulado>." >&2 && exit 1)
	uv run python -m pncp_ti.classificar.avaliar $(ROT)
