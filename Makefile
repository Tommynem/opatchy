.PHONY: sync format lint type test js test-e2e security-check ci validate release-dry-run

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
	uv run --locked --no-sync pytest -q tests/tooling/test_security_check.py

ci:
	uv lock --check
	uv sync --group dev --locked --check
	uv run --locked --no-sync python scripts/ci_policy.py --repository .
	uv run --locked --no-sync ruff format --check .
	uv run --locked --no-sync ruff check .
	uv run --locked --no-sync basedpyright
	uv run --locked --no-sync pytest -q --ignore=tests/tooling/test_controlled_runner_lifecycle.py
	uv run --locked --no-sync pytest -q --ignore=tests/tooling/test_controlled_runner_lifecycle.py --cov=helper/opatchy_helper --cov-report=term-missing
	node --test tests/js/*.test.mjs
	/usr/bin/python3 -m unittest discover -s tests/contract -p 'test_*.py'
	./scripts/runtime_without_venv.sh
	/usr/bin/python3 scripts/security_check.py
	git diff --check

validate:
	./scripts/validate.sh

release-dry-run:
	./scripts/release_readiness.py --repository . --tag v0.1.0 --dry-run --output-directory dist/release
