"""Integration tests for `config.yaml` options that don't require a relation."""

from __future__ import annotations

import jubilant


def test_is_juju_config():
    controller = jubilant.Juju(model="controller")

    controller.config("controller", {"is-juju": False})
    controller.wait(jubilant.all_active)

    config = controller.config("controller")
    assert config["is-juju"] is False

    controller.config("controller", reset=["is-juju"])
    controller.wait(jubilant.all_active)


def test_workload_tracing_tail_sampling_threshold_config():
    controller = jubilant.Juju(model="controller")

    controller.config(
        "controller", {"controller-url": "some_value"}
    )
    controller.wait(jubilant.all_active)

    config = controller.config("controller")
    assert config["controller-url"] == "some_value"

    controller.config("controller", reset=["controller-url"])
    controller.wait(jubilant.all_active)
