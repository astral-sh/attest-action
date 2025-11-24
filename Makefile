.PHONY: all
all:
	@echo "No default target, use 'lint' or 'fix'"

.PHONY: lint
lint:
	uv run --dev ruff format --check
	uv run --dev ruff check

.PHONY: fix
fix:
	uv run --dev ruff format
	uv run --dev ruff check --fix

.PHONY: pinact
pinact:
	pinact run --update --verify

.PHONY: test
test:
	uv run --dev pytest -s -o log_cli=true -o log_cli_level=DEBUG test.py
