# Development guide

You will need to have Python 3, Charmcraft and [uv](https://docs.astral.sh/uv/) installed.
```
sudo snap install charmcraft --classic --channel latest/stable
sudo snap install astral-uv --classic
```

## Setting up the environment

Create and activate a virtualenv with the development requirements:

```
uv venv
source .venv/bin/activate
uv sync --frozen --group dev
```

## Testing

This charm uses `make` to run its formatting, linting, and test commands
(following [charm-tech's command standardisation](https://github.com/canonical/charmcraft) conventions):

```console
$ make            # Runs lint and unit (the default target)
$ make format     # Auto-format code, and auto-fix trivial lint issues
$ make lint       # Report lint, format, static typing, and spelling issues
$ make unit       # Run unit tests (with coverage report)
$ make integration  # Run integration tests against a bootstrapped Juju controller
```

`make lint` will report errors but won't fix any file; use `make format` to
automatically fix trivial issues:

```console
$ make format
```

### Integration tests

Integration tests assume a Juju controller running this repo's
juju-controller charm has already been bootstrapped (they don't bootstrap or
destroy anything themselves). For local runs, bootstrap a controller with the
charm under test, e.g.:

```console
$ charmcraft pack
$ juju bootstrap lxd juju-controller-itest \
    --controller-charm-path=./juju-controller_*.charm
$ make integration
```

In CI, [concierge](https://github.com/canonical/concierge) is used to
provision the substrate (LXD, MicroK8s, or Canonical K8s) and bootstrap the
controller for each cloud in the integration test matrix; see
`.github/concierge-*.yaml` and `.github/workflows/ci.yml`.

## Deploying

Before you deploy your modified controller charm, you will need to pack it using Charmcraft:
```console
$ charmcraft pack
...
Charms packed:
    juju-controller_[...].charm
```

If deploying on LXD, you can bootstrap Juju using the `--controller-charm-path` flag, and providing the path to your packed charm.
```console
$ juju bootstrap lxd c --controller-charm-path=[path/to/packed/charm]
```

If deploying on k8s, you need to upload the charm to Charmhub first. Register a new charm name for testing:
```console
$ charmcraft register [new-name]
```
and upload the modified charm under this name:
```console
$ charmcraft upload *.charm --name [new-name] --release latest/stable
Revision 1 of [new-name] created
Revision released to latest/stable
```

Then, you can bootstrap a new k8s controller, providing the Charmhub name and channel:
```console
$ juju bootstrap microk8s c \
--controller-charm-path=[new-name]
--controller-charm-channel=latest/stable
```

## Releasing

To release a new version of the controller charm, first pack the charm as above:
```console
$ charmcraft pack
...
Charms packed:
    juju-controller_[...].charm
```

Then, upload under the name `juju-controller`:
```console
$ charmcraft upload *.charm --name juju-controller
Revision [XX] of 'juju-controller' created
```

Finally, release it to the relevant channels. Along with a `latest` track, we maintain a track for every minor version of Juju, e.g. `3.0`, `3.1`, etc.
```console
$ charmcraft release juju-controller --revision [XX] --channel latest/stable --channel 3.0/stable
Revision [XX] of charm 'juju-controller' released to latest/stable, 3.0/stable
```

You can also do the upload and release in a single step if you'd like:
```console
$ charmcraft upload *.charm --name juju-controller --release latest/stable --release 3.0/stable
Revision [XX] of 'juju-controller' created
Revision [XX] of charm 'juju-controller' released to latest/stable, 3.0/stable
```
