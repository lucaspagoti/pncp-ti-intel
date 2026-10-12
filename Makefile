.PHONY: up down test migrate ingest ingest-backfill backup restore eval

up: ## Sobe o Postgres local (porta só em 127.0.0.1).
	@test -f .env || (echo "Falta o .env. Copie .env.example para .env e preencha antes de rodar 'make up'." && exit 1)
	docker compose --env-file .env up -d
	@echo "Aguardando Postgres ficar saudável..."
	@timeout 60 bash -c 'until docker compose --env-file .env ps postgres | grep -q "(healthy)"; do sleep 1; done'
	@echo "Postgres pronto em 127.0.0.1:$${POSTGRES_PORT:-5432}."

down: ## Derruba os containers do projeto.
	docker compose down

test: ## Lint + format-check + testes (inclui snapshot e fumaça do compras-mcp).
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

migrate: ## Aplica as migrações do Alembic (schema, papéis ingest/mcp_reader, views).
	uv run alembic upgrade head

ingest: ## Ingestão diária (janela de ontem até hoje, todas as entidades).
	uv run python -m pncp_ti.ingest.cli --diario

ingest-backfill: ## Backfill histórico desde INGEST_BACKFILL_START (job longo — ver README).
	uv run python -m pncp_ti.ingest.cli --backfill

backup: ## pg_dump do Postgres local para backups/ (fora do Git).
	./scripts/backup_postgres.sh

restore: ## Restaura em banco NOVO: make restore DUMP=backups/arquivo.dump DATABASE=nome_novo
	@test -n "$(DUMP)" -a -n "$(DATABASE)" || (echo "Informe DUMP e DATABASE." && exit 1)
	./scripts/restore_postgres.sh "$(DUMP)" --database "$(DATABASE)"

eval: ## Ainda não implementado — chega na Fase 2 (filtro de TI e preços).
	@echo "make eval: nada a fazer ainda. Avaliações entram na Fase 2 (docs/FASES.md)."
