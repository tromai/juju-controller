"""Fixtures and helpers for Jubilant-based integration tests.

The `controller` fixture below bootstraps a real Juju controller using this
repo's packed juju-controller charm (via `--controller-charm-path`), once per
test session, and every test module reuses that same controller. This mirrors
`.github/workflows/ci.yml`, which now just installs Juju and hands off to
`pytest` -- there's no separate bootstrap/status-check shell step anymore.

Locally, you can run the whole thing with:

    charmcraft pack
    pip install jubilant pytest pyyaml
    pytest tests/integration -v

That will pack-discover `./juju-controller_*.charm`, bootstrap an LXD
controller named `juju-controller-itest`, wait for it to go active, run the
tests, then destroy the controller. Configure via environment variables:

  - JUJU_CONTROLLER_CHARM_PATH: path to the packed .charm file (default:
    autodetect a single `juju-controller_*.charm` in the repo root).
  - JUJU_ITEST_CLOUD: cloud to bootstrap on (default: "lxd").
  - JUJU_ITEST_BOOTSTRAP_BASE: value for `--bootstrap-base` (optional).
  - JUJU_ITEST_CONTROLLER_NAME: controller name (default:
    "juju-controller-itest").
  - JUJU_ITEST_KEEP_CONTROLLER: if set (to anything non-empty), don't destroy
    the controller after the test session -- useful for local debugging, and
    used in CI since the runner is thrown away anyway.

Some tests (metrics-endpoint, charm/workload tracing, loki-push-api) need a
provider charm that only ships for Kubernetes (prometheus-k8s,
tempo-coordinator-k8s, loki-k8s). Those tests are cross-model/cross-controller
and are skipped unless you point them at an existing microk8s controller via
the JUJU_ITEST_K8S_MODEL environment variable, for example:

    microk8s status --wait-ready
    juju bootstrap microk8s itest-k8s
    juju add-model cos
    export JUJU_ITEST_K8S_MODEL="itest-k8s:cos"
    pytest tests/integration -v
"""

from __future__ import annotations

import glob
import os
import pathlib
from collections.abc import Iterator

import jubilant
import pytest

_CHARM_PATH_ENV = "JUJU_CONTROLLER_CHARM_PATH"
_CLOUD_ENV = "JUJU_ITEST_CLOUD"
_BOOTSTRAP_BASE_ENV = "JUJU_ITEST_BOOTSTRAP_BASE"
_CONTROLLER_NAME_ENV = "JUJU_ITEST_CONTROLLER_NAME"
_KEEP_CONTROLLER_ENV = "JUJU_ITEST_KEEP_CONTROLLER"

_DEFAULT_CLOUD = "lxd"
_DEFAULT_CONTROLLER_NAME = "juju-controller-itest"


def _find_charm_path() -> str:
    """Resolve the packed juju-controller .charm to bootstrap with."""
    env_path = os.environ.get(_CHARM_PATH_ENV)
    if env_path:
        return str(pathlib.Path(env_path).resolve())

    charms = sorted(glob.glob("juju-controller_*.charm"))
    if not charms:
        pytest.fail(
            "No packed juju-controller charm found in the repo root. Run "
            "`charmcraft pack` first, or set JUJU_CONTROLLER_CHARM_PATH to the "
            ".charm file path."
        )
    return str(pathlib.Path(charms[0]).resolve())


@pytest.fixture(scope="session")
def controller() -> Iterator[jubilant.Juju]:
    """Bootstrap a Juju controller running this repo's packed juju-controller charm.

    Runs once for the whole test session; every test module reuses this same
    controller. `Juju.bootstrap()` has no `controller_charm_path` parameter, so
    the bootstrap itself goes through `Juju.cli()` directly; everything else
    uses the typed Jubilant API.
    """
    charm_path = _find_charm_path()
    cloud = os.environ.get(_CLOUD_ENV, _DEFAULT_CLOUD)
    bootstrap_base = os.environ.get(_BOOTSTRAP_BASE_ENV)
    controller_name = os.environ.get(_CONTROLLER_NAME_ENV, _DEFAULT_CONTROLLER_NAME)

    juju = jubilant.Juju()

    bootstrap_args = [
        "bootstrap",
        cloud,
        controller_name,
        "--controller-charm-path",
        charm_path,
    ]
    if bootstrap_base:
        bootstrap_args.extend(["--bootstrap-base", bootstrap_base])
    juju.cli(*bootstrap_args, include_model=False)

    juju.model = f"{controller_name}:controller"
    juju.wait(lambda status: jubilant.all_active(status, "controller"), timeout=600)

    yield juju

    if not os.environ.get(_KEEP_CONTROLLER_ENV):
        juju.cli(
            "destroy-controller",
            controller_name,
            "--destroy-all-models",
            "--no-prompt",
            "-y",
            include_model=False,
        )


@pytest.fixture(scope="session")
def k8s_juju() -> jubilant.Juju:
    """Return a Juju client for a pre-existing Kubernetes model.

    Used by tests that need a k8s-only COS charm (prometheus-k8s,
    tempo-coordinator-k8s, loki-k8s) related cross-model/cross-controller to
    the (machine-based) controller model. Skips if JUJU_ITEST_K8S_MODEL isn't
    set, since we can't safely bootstrap a whole second controller as a test
    fixture.
    """
    model = os.environ.get("JUJU_ITEST_K8S_MODEL")
    if not model:
        pytest.skip(
            "Set JUJU_ITEST_K8S_MODEL=<controller>:<model> (pointing at a microk8s "
            "controller/model) to run the cross-model COS tests."
        )
    return jubilant.Juju(model=model)


def cross_model_integrate(
    *,
    offerer: jubilant.Juju,
    offerer_app: str,
    offerer_endpoint: str,
    offer_name: str,
    consumer: jubilant.Juju,
    consumer_app: str,
    alias: str,
) -> None:
    """Offer an endpoint from one controller/model and consume+integrate it from another.

    This mirrors what `juju offer` / `juju consume` / `juju integrate` do across
    controllers, as shown in the README for relating juju-dashboard via a
    cross-model integration.
    """
    offerer.offer(offerer_app, endpoint=offerer_endpoint, name=offer_name)
    model_info = offerer.show_model()
    consumer.consume(
        f"{model_info.short_name}.{offer_name}",
        alias,
        controller=model_info.controller_name,
        owner="admin",
    )
    consumer.integrate(consumer_app, alias)


def cross_model_teardown(
    *,
    offerer: jubilant.Juju,
    offer_name: str,
    consumer: jubilant.Juju,
    consumer_app: str,
    alias: str,
) -> None:
    """Best-effort cleanup counterpart to `cross_model_integrate`."""
    try:
        consumer.remove_relation(consumer_app, alias)
    except jubilant.CLIError:
        pass
    try:
        consumer.remove_application(alias)
    except jubilant.CLIError:
        pass
    try:
        model_info = offerer.show_model()
        offerer.cli(
            "remove-offer",
            f"admin/{model_info.short_name}.{offer_name}",
            "-y",
            include_model=False,
        )
    except jubilant.CLIError:
        pass
