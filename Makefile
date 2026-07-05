.PHONY: up down test lint typecheck verify-audit-chain bench

up:
	docker compose up -d
	@echo "Valkey is up. Next: uv sync && uv run uvicorn app:app --app-dir gateway --port 8000"

down:
	docker compose down

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check core gateway tests

typecheck:
	uv run mypy core gateway

verify-audit-chain:
	uv run python scripts/verify_audit_chain.py

bench:
	@echo "bench harness lands in Phase 2 — see bench/README.md"
