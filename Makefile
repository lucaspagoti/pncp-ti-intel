.PHONY: up down test ingest eval

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

ingest: ## Ainda não implementado — chega na Fase 2 (base histórica).
	@echo "make ingest: nada a fazer ainda. Ingestão entra na Fase 2 (docs/FASES.md)."

eval: ## Ainda não implementado — chega na Fase 3 (filtro de TI e preços).
	@echo "make eval: nada a fazer ainda. Avaliações entram na Fase 3 (docs/FASES.md)."
