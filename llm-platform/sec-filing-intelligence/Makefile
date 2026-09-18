VENV ?= .venv
PY   := $(VENV)/bin/python

.PHONY: help install test lint fmt check serve mcp eval eval-offline demo web web-build docker clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install the package with dev extras
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

test: ## Run the test suite
	$(PY) -m pytest -q

lint: ## Lint
	$(VENV)/bin/ruff check .

fmt: ## Autofix lint findings
	$(VENV)/bin/ruff check . --fix

check: lint test ## Lint then test

serve: ## Run the HTTP API locally
	$(VENV)/bin/uvicorn filing_intel.api.app:app --reload --port 8000

mcp: ## Run the MCP server over stdio
	$(PY) -m filing_intel.mcp_server

eval: ## Run the eval suite against the configured provider
	$(PY) -m evals.harness --repeats 3 --json-out eval-report.json

eval-offline: ## Run the eval suite with the stub model against real EDGAR (no API key)
	$(PY) -m evals.harness --offline --repeats 2

web: ## Install and run the React UI against a local API (port 5173)
	cd web && npm install && npm run dev

web-build: ## Type-check and build the UI into web/dist
	cd web && npm install && npm run build

demo: web-build ## Build the UI and serve the whole app with no API key needed
	FILING_INTEL_PROVIDER=demo $(VENV)/bin/uvicorn filing_intel.api.app:app --port 8000

docker: ## Build and run the API plus Redis
	docker compose up --build

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info eval-report.json
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
