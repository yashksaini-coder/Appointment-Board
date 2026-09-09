.DEFAULT_GOAL := help

# Local (non-Docker) development points at the database docker compose runs.
DATABASE_URL ?= postgresql+psycopg://appointments:appointments@localhost:5432/appointments
export DATABASE_URL

VENV    := .venv
BIN     := $(VENV)/bin
COMPOSE := docker compose -f ../docker-compose.yml

.PHONY: help setup dev serve test lint db-up up down restart logs psql migrate reset clean

help: ## Show the available commands
	@echo "Appointment Board - backend"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Quick start:  make setup && make db-up && make dev"

# --------------------------------------------------------------- environment

setup: ## Create the virtualenv with uv and install dependencies
	uv venv $(VENV)
	uv pip install --python $(BIN)/python -r requirements.txt
	@echo "Ready. Activate with: source $(VENV)/bin/activate"

$(BIN)/uvicorn:
	@echo "No virtualenv yet - run 'make setup' first." && exit 1

# ------------------------------------------------------------------- running

dev: $(BIN)/uvicorn ## Run the API with autoreload on :8000
	$(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

serve: $(BIN)/uvicorn ## Run the API the way production does (4 workers, JSON logs)
	LOG_FORMAT=json $(BIN)/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

test: ## Run the test suite (needs PostgreSQL - try 'make db-up')
	$(BIN)/python -m pytest -q

lint: ## Byte-compile every module to catch syntax errors
	$(BIN)/python -m compileall -q app tests

# -------------------------------------------------------------------- docker

db-up: ## Start only PostgreSQL, for local development outside Docker
	$(COMPOSE) up -d db

up: ## Build and start the whole stack
	$(COMPOSE) up -d --build

down: ## Stop the stack
	$(COMPOSE) down

restart: ## Restart just the backend container
	$(COMPOSE) restart backend

logs: ## Follow the backend logs
	$(COMPOSE) logs -f backend

psql: ## Open a psql shell on the database
	$(COMPOSE) exec db psql -U appointments -d appointments

migrate: ## Apply database migrations (see docs/DEPLOYMENT.md)
	$(BIN)/alembic upgrade head

# ------------------------------------------------------------------- cleanup

reset: ## Destroy the database volume and start again with sample data
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build

clean: ## Remove the virtualenv and Python caches
	rm -rf $(VENV) .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
