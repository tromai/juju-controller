# Copyright 2026 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

"""Integration tests for config options that don't require a relation.

Setting any option runs the charm's config-changed hook, which pushes the
workload tracing config to the controller over its control socket, so this
also checks that round trip works on a real controller.
"""

from __future__ import annotations

from collections.abc import Iterator

import _helpers
import jubilant
import pytest

APP = _helpers.CONTROLLER_APP


@pytest.fixture
def reset_config(controller: jubilant.Juju) -> Iterator[list[str]]:
    """Collect option names to reset after the test, and wait for the charm to settle."""
    options: list[str] = []
    yield options
    if options:
        controller.config(APP, reset=options)
        _helpers.wait_controller_active(controller)


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("is-juju", False),
        ("controller-url", "wss://controller.example.com:17070/api"),
        ("identity-provider-url", "https://candid.example.com"),
        ("workload-tracing-stack-traces", True),
        ("workload-tracing-sample-ratio", 0.5),
        ("workload-tracing-tail-sampling-threshold", "5ms"),
        ("workload-tracing-insecure-skip-verify", True),
    ],
)
def test_set_config(
    controller: jubilant.Juju,
    reset_config: list[str],
    option: str,
    value: jubilant.ConfigValue,
):
    reset_config.append(option)
    controller.config(APP, {option: value})
    _helpers.wait_controller_active(controller)

    assert controller.config(APP)[option] == value


def test_invalid_workload_tracing_sample_ratio_blocks(
    controller: jubilant.Juju, reset_config: list[str]
):
    """An out-of-range sample ratio blocks the charm until it's fixed."""
    reset_config.append("workload-tracing-sample-ratio")
    controller.config(APP, {"workload-tracing-sample-ratio": 1.5})

    status = controller.wait(
        lambda status: jubilant.all_blocked(status, APP),
        error=lambda status: jubilant.any_error(status, APP),
        delay=_helpers.POLL_DELAY,
        timeout=_helpers.SETTLE_TIMEOUT,
    )
    assert "workload-tracing-sample-ratio" in status.apps[APP].app_status.message

    # The reset_config teardown checks the charm goes back to active.
