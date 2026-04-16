.PHONY: setup venv install install-ml db-up db-down api worker test test-unit test-integration \
        migrate local-upload local-search seed lint clean help

VENV        := .venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
PYTEST      := $(VENV)/bin/pytest
PYTHONPATH  := .:apps/api
API_PORT    ?= 8000

# ── Setup ─────────────────────────────────────────────────────────────────────

setup: venv install db-up migrate ## Full first-run setup
	@cp -n .env.example .env 2>/dev/null || true
	@echo ""
	@echo "Setup complete. Edit .env then run: make api"

venv: ## Create Python virtual environment
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip -q

install: venv ## Install core dependencies
	$(PIP) install -r apps/api/requirements.txt -q
	$(PIP) install -r workers/ingestion_worker/requirements.txt -q
	$(PIP) install pytest pytest-asyncio anyio -q

install-ml: venv ## Install heavy ML deps (transformers + torch) for SigLIP2 / local Gemma
	$(PIP) install "transformers>=4.44.0" "torch>=2.2.0" "accelerate>=0.33.0" -q

# ── Database ──────────────────────────────────────────────────────────────────

db-up: ## Start Postgres with pgvector in Docker
	docker compose up postgres -d
	@echo "Waiting for Postgres…"
	@sleep 3

db-down: ## Stop Postgres
	docker compose down

migrate: ## Create/update database tables
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m app.db.migrations.create_tables

# ── Running services ──────────────────────────────────────────────────────────

api: ## Start the FastAPI development server (hot-reload)
	PYTHONPATH=$(PYTHONPATH) $(VENV)/bin/uvicorn app.main:app \
	    --app-dir apps/api \
	    --host 0.0.0.0 --port $(API_PORT) --reload

worker: ## Start the ingestion worker
	PYTHONPATH=.:apps/api $(PYTHON) -m workers.ingestion_worker.main

docker-up: ## Start all services via docker-compose
	docker compose up --build

docker-down: ## Stop all docker services
	docker compose down

# ── Testing ───────────────────────────────────────────────────────────────────

test: test-unit ## Run all tests that don't need a running DB

test-unit: ## Run unit tests (no DB or network needed)
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/unit/ -v

test-integration: ## Run integration tests (requires running Postgres)
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/integration/ -v

# ── Dev utilities ─────────────────────────────────────────────────────────────

local-upload: ## Upload a file via the API: make local-upload FILE=path/to/file.pdf
ifndef FILE
	$(error FILE is not set. Usage: make local-upload FILE=path/to/file.pdf)
endif
	curl -s -X POST http://localhost:$(API_PORT)/upload/local \
	    -F "file=@$(FILE)" | python3 -m json.tool

local-search: ## Search the index: make local-search Q="your query here"
ifndef Q
	$(error Q is not set. Usage: make local-search Q="your query")
endif
	curl -s -X POST http://localhost:$(API_PORT)/search \
	    -H "Content-Type: application/json" \
	    -d '{"query": "$(Q)", "topK": 5, "includeAnswer": true}' \
	    | python3 -m json.tool

seed: ## Run the seed script to create demo data
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/seed_demo_data.py

lint: ## Check code style (requires ruff)
	$(VENV)/bin/ruff check apps/ workers/ tests/ 2>/dev/null || \
	    echo "Install ruff: pip install ruff"

clean: ## Remove venv, cache, and temp files
	rm -rf $(VENV) .pytest_cache __pycache__ apps/api/app/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	    awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
