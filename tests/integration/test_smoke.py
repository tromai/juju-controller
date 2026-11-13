# Copyright 2026 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

"""Smoke integration test for the juju-controller charm."""

from __future__ import annotations

import _helpers
import jubilant


def test_controller_charm_is_active(controller: jubilant.Juju):
    """The juju-controller charm reaches active status after bootstrap."""
    # Same 600s budget as the shell loop this replaced in CI. Fail straight
    # away if the charm goes into error rather than waiting out the timeout.
    _helpers.wait_controller_active(controller, timeout=10 * 60)
