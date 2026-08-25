.PHONY: sync format lint type test js validate

sync:
	uv sync --group dev

format:
	uv run --locked --no-sync ruff format --check .

lint:
	uv run --locked --no-sync ruff check .

type:
	uv run --locked --no-sync basedpyright

test:
	uv run --locked --no-sync pytest -q

js:
	node --test tests/js/*.test.mjs

validate:
	./scripts/validate.sh
