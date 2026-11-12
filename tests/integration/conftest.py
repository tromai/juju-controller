# Copyright 2026 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

"""Fixtures for the Jubilant-based integration tests.

These tests **assume a Juju controller has already been bootstrapped** with
this repo's juju-controller charm. Nothing here bootstraps or destroys a
controller. For example:

    charmcraft pack
    juju bootstrap lxd lxd --controller-charm-path=./juju-controller_ubuntu@24.04-amd64.charm
    uv run --group integration pytest tests/integration -v --log-cli-level=INFO

The controller under test is the one selected by pytest-jubilant's
``--juju-controller`` option (default: the current Juju controller). Temporary
models created through pytest-jubilant's ``juju_factory`` fixture are created
on that controller as well, and are destroyed at module teardown (unless
``--no-juju-teardown`` is passed).

Some tests are ports of the upstream juju/juju ``tests/suites/controllercharm``
suite and need ``prometheus-k8s``, which only runs on Kubernetes:

- ``test_prometheus.py`` and ``test_prometheus_multi.py`` deploy Prometheus
  next to the controller, so they only run when the controller under test is
  on a Kubernetes cloud (like upstream's ``BOOTSTRAP_PROVIDER=k8s``).
- ``test_prometheus_cmr.py`` deploys Prometheus on a *second* controller,
  which must be on a Kubernetes cloud, and relates it across controllers. It
  only runs if that controller is passed with ``--k8s-controller`` (like
  upstream's ``K8S_CLOUD``). For example:

      juju bootstrap microk8s k8s
      uv run --group integration pytest tests/integration -v \\
          --juju-controller=lxd --k8s-controller=k8s

Plain helper functions shared by the test modules live in ``_helpers.py``.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator

import jubilant
import pytest

logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the options that are specific to this test suite."""
    parser.addoption(
        "--k8s-controller",
        action="store",
        default=None,
        help=(
            "Name of an existing Juju controller on a Kubernetes cloud. It hosts prometheus-k8s "
            "in the cross-controller test (test_prometheus_cmr.py), which is skipped otherwise."
        ),
    )


@pytest.fixture(scope="session")
def controller(request: pytest.FixtureRequest) -> jubilant.Juju:
    """Return a Juju client for the controller model of the controller under test.

    The controller under test is the one passed with ``--juju-controller``, or
    the current Juju controller if the option isn't set.
    """
    controller_name: str | None = request.config.getoption("--juju-controller")
    model = f"{controller_name}:controller" if controller_name else "controller"
    return jubilant.Juju(model=model)


@pytest.fixture(scope="session")
def controller_info(controller: jubilant.Juju) -> jubilant.ModelInfo:
    """Return ``juju show-model`` details for the controller model."""
    return controller.show_model()


@pytest.fixture(scope="module")
def require_k8s_controller(controller_info: jubilant.ModelInfo) -> None:
    """Skip the test unless the controller under test is on a Kubernetes cloud.

    Equivalent to the ``case "${BOOTSTRAP_PROVIDER:-}" in "k8s")`` switch in
    upstream's ``test_prometheus``.
    """
    if controller_info.model_type != "caas":
        pytest.skip(
            f"needs a controller on a Kubernetes cloud to deploy prometheus-k8s next to, but "
            f"controller {controller_info.controller_name!r} is on cloud "
            f"{controller_info.cloud!r} ({controller_info.model_type})"
        )


@pytest.fixture(scope="module")
def k8s_controller(request: pytest.FixtureRequest) -> str:
    """Return the name of the controller passed with ``--k8s-controller``, or skip."""
    name: str | None = request.config.getoption("--k8s-controller")
    if not name:
        pytest.skip("pass --k8s-controller=<controller on a Kubernetes cloud> to run this test")
    return name


@pytest.fixture(scope="module")
def metrics_offer(
    request: pytest.FixtureRequest,
    controller: jubilant.Juju,
    controller_info: jubilant.ModelInfo,
) -> Iterator[str]:
    """Offer the controller charm's ``metrics-endpoint``, and yield the offer URL.

    Equivalent to upstream's ``juju offer controller.controller:metrics-endpoint``.

    Unlike upstream, the controller isn't bootstrapped afresh for each test, so
    each test module gets an offer with a unique name, and the offer (with any
    relation left behind) is removed at module teardown, unless
    ``--no-juju-teardown`` is passed. The returned URL is fully qualified
    (``<controller>:<qualifier>/controller.<offer>``), so it can be consumed
    from any controller.
    """
    module_name = request.module.__name__.rpartition(".")[-1]
    suffix = module_name.removeprefix("test_").replace("_", "-")
    offer_name = f"metrics-{suffix}-{secrets.token_hex(2)}"

    controller.offer("controller", endpoint="metrics-endpoint", name=offer_name)
    offer_url = f"{controller_info.controller_name}:{controller_info.name}.{offer_name}"
    logger.info("Offered controller:metrics-endpoint as %s", offer_url)

    yield offer_url

    if request.config.getoption("--no-juju-teardown"):
        return
    try:
        controller.cli("remove-offer", offer_url, "--force", "--yes", include_model=False)
    except jubilant.CLIError as e:
        # Don't fail (or mask the real failure of) the test because of cleanup.
        logger.warning("Failed to remove offer %s: %s", offer_url, e.stderr)
