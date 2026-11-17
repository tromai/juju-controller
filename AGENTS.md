# juju-controller Agent Rules Index

Ensure that the following documents have been read:

 - [Juju Hook Lifecycle](https://documentation.ubuntu.com/juju/3.6/reference/hook/)
 - [Operator Framework](https://documentation.ubuntu.com/ops/latest/reference/)

If guidance conflicts, Juju Hook Lifecycle rules take precedence.

## Setup

Create and activate a virtualenv, and install the development requirements:
   
```
virtualenv -p python3 venv
source venv/bin/activate
uv pip install ".[dev]"
```

Install `astral-uv` using snaps:

```
sudo snap install astral-uv --classic
```

## Build

Install `charmcraft` using snaps:

```
sudo snap install charmcraft --classic
```

Then run charmcraft pack:

```
charmcraft pack -v
```

## Updating libs

```
charmcraft fetch-libs
```

## Running Tests

- `./run_tests`
- Integration tests need an already-bootstrapped controller running this charm:
  `uv run --group integration pytest tests/integration -v --juju-controller=<controller>`
  (see CONTRIBUTING.md).
