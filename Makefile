.PHONY: test lint format servir

# Os dois gates do repo (AGENTS.md, "Validar antes do PR").
test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff check --fix . && uv run ruff format .

servir:
	uv run python -m frentes servir
