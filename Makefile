# NyayaLens developer commands. CI runs the same targets, so "make check"
# passing locally means CI passes too.

PY := .venv/bin/python
VENV := .venv
PORT ?= 8080

.DEFAULT_GOAL := help
.PHONY: help install dev dev-fake lint format typecheck security test test-fast e2e eval laws-data check lock clean deploy

help: ## Show the available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

$(VENV): requirements.txt requirements-dev.txt
	python3.12 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	@touch $(VENV)

install: $(VENV) ## Create the virtualenv and install everything

dev: install ## Run the app against the real Gemini API (needs a key in .env)
	$(PY) -m uvicorn app.main:app --reload --port $(PORT) --proxy-headers

dev-fake: install ## Run the app offline with the deterministic fake provider
	LLM_PROVIDER=fake LAW_DATA_SHOW_UNREVIEWED=true \
		$(PY) -m uvicorn app.main:app --reload --port $(PORT)

lint: ## Check formatting, lint rules and the frontend
	$(VENV)/bin/ruff check app tests scripts evals
	$(VENV)/bin/ruff format --check app tests scripts evals
	npx --yes eslint frontend

format: ## Apply formatting and safe lint fixes
	$(VENV)/bin/ruff check --fix app tests scripts evals
	$(VENV)/bin/ruff format app tests scripts evals

typecheck: ## Run mypy in strict mode
	$(VENV)/bin/mypy app scripts

security: ## Run the security scanners
	$(VENV)/bin/bandit -q -c pyproject.toml -r app scripts
	$(VENV)/bin/pip-audit -r requirements.txt --strict

test: install ## Run backend tests with coverage, plus the frontend unit tests
	$(PY) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 \
		--ignore=tests/e2e
	node --test frontend/tests

test-fast: ## Run backend tests without coverage
	$(PY) -m pytest --ignore=tests/e2e -q

e2e: install ## Run the browser and accessibility tests
	$(PY) -m playwright install --with-deps chromium
	$(PY) -m pytest tests/e2e -q

eval: install ## Run the live evaluation suite (needs a real API key)
	$(PY) evals/run.py

laws-data: install ## Rebuild law data from the official PDFs in data_sources/
	$(PY) scripts/build_law_data.py

check: lint typecheck security test ## Everything CI runs, except the browser tests

lock: install ## Re-pin requirements.txt from requirements.in
	$(PY) -m pip install -r requirements.in
	$(PY) -m pip freeze --exclude-editable > requirements.txt

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

deploy: ## Deploy to Cloud Run
	./scripts/deploy.sh
