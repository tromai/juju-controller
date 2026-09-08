"""Smoke integration test for the juju-controller charm.

This assumes a Juju controller running this repo's juju-controller charm has
already been bootstrapped (see `conftest.py`). It just checks that the
`controller` application in the `controller` model reaches active status.
"""

from __future__ import annotations

import jubilant


def test_controller_charm_is_active(controller: jubilant.Juju) -> None:
    """The juju-controller charm reaches active status after bootstrap."""
    controller.wait(
        lambda status: jubilant.all_active(status, "controller"),
        timeout=10 * 60,
    )
