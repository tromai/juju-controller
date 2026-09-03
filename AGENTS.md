# juju-controller Agent Rules Index

Ensure that the following documents have been read:

 - [Juju Hook Lifecycle](https://documentation.ubuntu.com/juju/3.6/reference/hook/)
 - [Operator Framework](https://documentation.ubuntu.com/ops/latest/reference/)

If guidance conflicts, Juju Hook Lifecycle rules take precedence.

## Setup

Install `astral-uv` using snaps:

```
sudo snap install astral-uv --classic
```

Create and activate a virtualenv, and install the development requirements:
   
```
uv venv
source .venv/bin/activate
uv sync --frozen --extra dev
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
