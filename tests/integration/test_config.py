"""Integration tests for `config.yaml` options that don't require a relation."""

from __future__ import annotations

import jubilant


def test_is_juju_config(controller: jubilant.Juju):
    controller.config("controller", {"is-juju": False})
    controller.wait(jubilant.all_active, timeout=30)

    config = controller.config("controller")
    assert config["is-juju"] is False

    controller.config("controller", reset=["is-juju"])
    controller.wait(jubilant.all_active, timeout=30)


def test_workload_tracing_tail_sampling_threshold_config(controller: jubilant.Juju):
    controller.config(
        "controller", {"workload-tracing-tail-sampling-threshold": "5ms"}
    )
    controller.wait(jubilant.all_active, timeout=30)

    config = controller.config("controller")
    assert config["workload-tracing-tail-sampling-threshold"] == "5ms"

    controller.config("controller", reset=["workload-tracing-tail-sampling-threshold"])
    controller.wait(jubilant.all_active, timeout=30)
