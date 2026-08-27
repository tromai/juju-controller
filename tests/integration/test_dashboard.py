"""Integration tests for the `dashboard` (juju-dashboard) endpoint."""

from __future__ import annotations

import yaml
import jubilant


def test_dashboard_relation_sets_app_data(controller: jubilant.Juju):
    controller.deploy("juju-dashboard", channel="beta")
    controller.integrate("controller", "juju-dashboard")
    controller.wait(jubilant.all_active)

    # The controller charm sets controller-url/identity-provider-url/is-juju
    # as *application* data on the dashboard relation (see
    # `_on_dashboard_relation_joined` in src/charm.py). Read it back via
    # relation-get on the dashboard side.
    raw = controller.cli(
        "exec",
        "--unit",
        "juju-dashboard/0",
        "--",
        "relation-get",
        "-r",
        "controller:dashboard",
        "--app",
        "-",
        "controller",
        "--format=yaml",
    )
    data = yaml.safe_load(raw)
    assert "controller-url" in data
    assert "identity-provider-url" in data
    assert "is-juju" in data


def test_dashboard_relation_reflects_config_changes(controller: jubilant.Juju):
    controller.config("controller", {"controller-url": "wss://example.test:17070"})
    controller.wait(jubilant.all_active)

    raw = controller.cli(
        "exec",
        "--unit",
        "juju-dashboard/0",
        "--",
        "relation-get",
        "-r",
        "controller:dashboard",
        "--app",
        "-",
        "controller",
        "--format=yaml",
    )
    data = yaml.safe_load(raw)
    assert data["controller-url"] == "wss://example.test:17070"

    # Restore default for subsequent tests.
    controller.config("controller", reset=["controller-url"])
    controller.wait(jubilant.all_active)


def test_remove_dashboard(controller: jubilant.Juju):
    controller.remove_application("juju-dashboard")
    controller.wait(
        lambda status: "juju-dashboard" not in status.apps and jubilant.all_active(status)
    )
