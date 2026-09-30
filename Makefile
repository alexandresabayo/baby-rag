.PHONY: help up down ingest reindex verify backend-dev frontend-dev test lint fmt

help:  ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

up:  ## Start the full stack with Docker Compose
	docker compose up --build -d

down:  ## Stop the stack
	docker compose down

ingest:  ## Index the corpus (stop the backend first in persistent Chroma mode)
	cd backend && $$(test -f ../.venv/bin/python && echo ../.venv/bin/python || echo python3) -m app.cli ingest

reindex:  ## Recreate the Chroma collection and re-embed all chunks
	cd backend && $$(test -f ../.venv/bin/python && echo ../.venv/bin/python || echo python3) -m app.cli reindex

verify:  ## Check SQLite/Chroma consistency and FTS integrity
	cd backend && $$(test -f ../.venv/bin/python && echo ../.venv/bin/python || echo python3) -m app.cli verify

backend-dev:  ## Run the API dev server on :8000
	cd backend && $$(test -f ../.venv/bin/python && echo ../.venv/bin/python || echo uv) run uvicorn app.main:app --reload --port 8000

frontend-dev:  ## Run the Vite dev server on :5173
	cd frontend && npm run dev

test:  ## Run backend and frontend test suites
	cd backend && FAKE_PROVIDERS=1 $$(test -f ../.venv/bin/python && echo ../.venv/bin/python || echo python3) -m pytest tests/ -q
	cd frontend && npm test

lint:  ## Ruff (Python) and ESLint (JS)
	cd backend && $$(test -f ../.venv/bin/ruff && echo ../.venv/bin/ruff || echo ruff) check app
	cd frontend && npm run lint

fmt:  ## Auto-format Python code
	cd backend && $$(test -f ../.venv/bin/ruff && echo ../.venv/bin/ruff || echo ruff) check app --fix
