.PHONY: test lint format servir db

# Postgres de desenvolvimento e testes (porta 55439). Os testes precisam dele no ar.
db:
	docker compose --profile dev up -d --wait db

# Os dois gates do repo (AGENTS.md, "Validar antes do PR").
test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff check --fix . && uv run ruff format .

servir:
	uv run python -m eventos servir
