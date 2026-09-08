"""Fixtures for the Jubilant-based smoke integration test.

These tests **assume a Juju controller has already been bootstrapped** and
is running this repo's juju-controller charm in its `controller` model (see
`test_smoke.py`). Nothing here bootstraps or destroys a controller -- do
that yourself first, for example:

    charmcraft pack
    juju bootstrap lxd juju-controller-itest \\
        --controller-charm-path=./juju-controller_*.charm
    make integration

In CI, `.github/concierge-*.yaml` (via `concierge prepare`) provisions the
substrate and bootstraps the controller for each cloud in the integration
test matrix; see `.github/workflows/ci.yml`.
"""

from __future__ import annotations

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
