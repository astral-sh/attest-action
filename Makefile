.PHONY: all
all:
	@echo "No default target, use 'lint' or 'fix'"

.PHONY: lint
lint:
	uvx ruff format --check
	uvx ruff check

.PHONY: fix
fix:
	uvx ruff format
	uvx ruff check --fix

.PHONY: test
test:
	uvx --with=requests --with-requirements=action.py pytest -s -o log_cli=true -o log_cli_level=DEBUG test.py
