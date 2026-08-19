# We're using Make as a command runner, so always make (avoids need for .PHONY)
MAKEFLAGS += --always-make

export PYTHONPATH := $(CURDIR)/lib:$(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH),)

all: lint unit

# Please keep the list below in alphabetical order.

fix:
	# Run check --fix first so any resulting edits get formatted below.
	uv run --group dev ruff check --fix --preview
	uv run --group dev ruff format --preview

format:
	uv run --group dev ruff format --preview

lint:
	uv run --frozen --group dev ruff check --preview
	uv run --frozen --group dev ruff format --preview --check
	uv run --frozen --group dev pyright
	uv run --frozen --group dev codespell

unit:
	uv run --frozen --group dev coverage run --source=src --branch -m unittest -v $(ARGS)
	uv run --frozen --group dev coverage report -m