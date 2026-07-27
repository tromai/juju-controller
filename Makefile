.PHONY: format lint unit integration

format:
	ruff format
	ruff check --fix

lint:
	ruff check
	pyright
	codespell

unit:
	PYTHONPATH="src:lib" coverage run --source=src -m unittest -v
	coverage report -m

integration:
	juju status --format=json > /dev/null 2>&1 || (echo "Juju controller not bootstrapped. Please bootstrap first." && exit 1)
	@echo "No integration tests defined yet."
