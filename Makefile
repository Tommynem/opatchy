.PHONY: sync format lint type test js test-e2e security-check validate

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

test-e2e:
	uv run --locked --no-sync pytest -q tests/e2e tests/python/test_runner.py tests/python/test_storage.py tests/tooling/test_controlled_runner_lifecycle.py

security-check:
	/usr/bin/python3 scripts/security_check.py

validate:
	./scripts/validate.sh
