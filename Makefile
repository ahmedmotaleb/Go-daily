# Go Daily developer commands. Run `make help` for the list.

SHELL := /bin/bash
API_DIR := apps/api
WEB_DIR := apps/admin-web
UV := uv --directory $(API_DIR)

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available commands
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[32m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup
.PHONY: setup
setup: ## Install API and web dependencies, create .env if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — edit it.")
	$(UV) sync
	pnpm install

# ---------------------------------------------------------------- run
.PHONY: dev api-dev web-dev
dev: ## Run API and admin web with auto-reload (needs a running PostgreSQL)
	@trap 'kill 0' EXIT; $(MAKE) api-dev & $(MAKE) web-dev & wait

api-dev: ## Run the API with auto-reload on :8000
	$(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web-dev: ## Run the admin web dev server on :3000
	pnpm --filter admin-web dev

.PHONY: up down logs
up: ## Start the full stack in Docker (postgres, migrate, api, admin-web)
	docker compose up --build -d

down: ## Stop the Docker stack
	docker compose down

logs: ## Follow Docker stack logs
	docker compose logs -f

# ---------------------------------------------------------------- database
.PHONY: migrate migration seed bootstrap-admin
migrate: ## Apply database migrations
	$(UV) run alembic upgrade head

migration: ## Create a migration: make migration m="describe change"
	@test -n "$(m)" || (echo 'usage: make migration m="describe change"' && exit 1)
	$(UV) run alembic revision --autogenerate -m "$(m)"

seed: ## Seed reference data (idempotent; no fake operational data)
	$(UV) run python -m app.cli seed

bootstrap-admin: ## Create the first SUPER_ADMIN from BOOTSTRAP_ADMIN_* env vars
	$(UV) run python -m app.cli bootstrap-admin

# ---------------------------------------------------------------- quality
.PHONY: test api-test web-test android-test lint api-lint web-lint typecheck format build check
test: api-test web-test ## Run all tests

api-test: ## Run API tests (needs PostgreSQL; uses TEST_DATABASE_URL)
	$(UV) run pytest

web-test: ## Run admin web unit tests
	pnpm --filter admin-web test

android-test: ## Run driver app core tests (needs JDK 17+; no Android SDK)
	cd apps/driver-android && ./gradlew -p core test

lint: api-lint web-lint ## Lint everything

api-lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

web-lint:
	pnpm --filter admin-web lint
	pnpm --filter admin-web format:check

typecheck: ## Type-check API (mypy) and web (tsc)
	$(UV) run mypy app tests
	pnpm --filter admin-web typecheck

format: ## Auto-format code
	$(UV) run ruff check --fix .
	$(UV) run ruff format .
	pnpm --filter admin-web format

build: ## Production build of the admin web
	pnpm --filter admin-web build

check: lint typecheck test build ## Everything CI runs
