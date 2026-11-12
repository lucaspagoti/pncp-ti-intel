.PHONY: up down test e2e migrate ingest web refresh-busca smoke-web backup restore amostra eval operacao mcp

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

E2E_SAIDA ?= qa-out/e2e

e2e: ## E2E da web no Chromium (Playwright); fora do CI e do QA, usa scripts/playwright_libs.sh.
	@if [ -z "$$CI" ] && [ -z "$$FONTCONFIG_FILE" ]; then eval "$$(scripts/playwright_libs.sh)"; fi; \
	PNCP_TI_E2E=1 uv run pytest tests/e2e --browser chromium \
		--screenshot only-on-failure --output $(E2E_SAIDA)

migrate: ## Aplica as migrações do Alembic (schema, papéis, views).
	uv run alembic upgrade head

FONTE ?= siga

ingest: ## Carga de uma fonte: make ingest FONTE=siga|proderj|arp|pncp_busca [ARGS=--validar].
	@case "$(FONTE)" in siga|proderj|arp|pncp_busca) ;; *) echo "FONTE=$(FONTE) desconhecida (siga|proderj|arp|pncp_busca)." >&2; exit 1;; esac
	uv run python -m pncp_ti.fontes.$(FONTE) $(ARGS)

web: ## Web local em 127.0.0.1:8000 (papel web_reader; precisa de PNCP_TI_WEB_PASSWORD).
	uv run python -m pncp_ti.web

refresh-busca: ## Atualiza a busca materializada da web (a carga já faz isso ao publicar).
	uv run python -m pncp_ti.busca

smoke-web: ## Smoke da web em execução (WEB_URL, padrão http://127.0.0.1:8000).
	./scripts/smoke_web.sh

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

operacao: ## Alertas e digest (bridge configurada no .env).
	uv run python -m pncp_ti.operacao diaria

mcp: ## Servidor MCP local, somente stdio e SELECT em views.
	uv run python -m pncp_ti.mcp_server
