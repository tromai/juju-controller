.DEFAULT_GOAL := help

.PHONY: all help format lint unit integration

all: lint unit  ## Run lint and unit tests (the default target)

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

format:  ## Format and auto-fix with ruff
	uv run --extra dev ruff check --preview --fix
	uv run --extra dev ruff format --preview

lint: ## Lint with ruff, type-check with pyright, and check code spelling with codespell
	uv run --extra dev ruff check --preview
	uv run --extra dev ruff format --preview --check
	PYTHONPATH=src:lib uv run --extra dev pyright
	uv run --extra dev codespell

unit:  ## Run unit tests. To provide extra args, use: make unit ARGS='extra_args'
	PYTHONPATH=src:lib uv run --extra dev coverage run --source=src -m unittest -v $(ARGS)
	uv run --extra dev coverage report -m

integration:  ## Run integration tests
	uv run --extra integration pytest tests/integration -v --log-cli-level=INFO
