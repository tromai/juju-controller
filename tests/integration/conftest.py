"""Fixtures for Jubilant-based integration tests.

Unlike an earlier version of this file, these tests **assume a Juju
controller has already been bootstrapped** and is running this repo's
juju-controller charm in its `controller` model (see `test_config.py` /
`test_smoke.py` for the simplest examples: they just do
`jubilant.Juju(model="controller")` and go). Nothing here bootstraps or
destroys a controller -- do that yourself first, for example:

    charmcraft pack
    juju bootstrap lxd juju-controller-itest \\
        --controller-charm-path=./juju-controller_*.charm
    pip install jubilant pytest pyyaml
    pytest tests/integration -v

Some tests (`test_prometheus.py`, `test_prometheus_multi.py`,
`test_prometheus_cmr.py`) need a provider charm that only ships for
Kubernetes (`prometheus-k8s`). Those tests are cross-model/cross-controller
and are skipped unless you point them at an existing k8s controller/model
via the JUJU_ITEST_K8S_MODEL environment variable, for example:

    microk8s status --wait-ready
    juju bootstrap microk8s itest-k8s
    juju add-model cos
    export JUJU_ITEST_K8S_MODEL="itest-k8s:cos"
    pytest tests/integration -v

Non-fixture helpers shared across test modules (cross-model offer/consume,
Prometheus targets-API polling, etc.) live in `_helpers.py`, since fixtures
and plain helper functions serve different purposes and `_helpers.py` can be
imported directly from test modules (`import _helpers`), unlike `conftest.py`.
"""

from __future__ import annotations

import os

import jubilant
import pytest


@pytest.fixture(scope="session")
def controller() -> jubilant.Juju:
    """Return a Juju client for the already-bootstrapped controller model.

    This assumes a Juju controller running this repo's juju-controller
    charm has already been bootstrapped (see the module docstring above) --
    it does not bootstrap or destroy anything itself.
    """
    return jubilant.Juju(model="controller")


@pytest.fixture(scope="session")
def k8s_juju() -> jubilant.Juju:
    """Return a Juju client for a pre-existing Kubernetes model.

    Used by tests that need a k8s-only COS charm (prometheus-k8s) related
    cross-model/cross-controller to the (machine-based) controller model.
    Skips if JUJU_ITEST_K8S_MODEL isn't set, since we can't safely bootstrap
    a whole second controller as a test fixture.
    """
    model = os.environ.get("JUJU_ITEST_K8S_MODEL")
    if not model:
        pytest.skip(
            "Set JUJU_ITEST_K8S_MODEL=<controller>:<model> (pointing at a microk8s "
            "controller/model) to run the cross-model COS tests."
        )
    return jubilant.Juju(model=model)
