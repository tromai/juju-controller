"""Integration tests for `config.yaml` options that don't require a relation."""

from __future__ import annotations

import jubilant


def test_is_juju_and_identity_provider_url_config(controller: jubilant.Juju):
    controller.config(
        "controller",
        {
            "is-juju": False,
            "identity-provider-url": "https://idp.example.test",
        },
    )
    controller.wait(jubilant.all_active)

    config = controller.config("controller")
    assert config["is-juju"] is False
    assert config["identity-provider-url"] == "https://idp.example.test"

    controller.config("controller", reset=["is-juju", "identity-provider-url"])
    controller.wait(jubilant.all_active)


def test_workload_tracing_tail_sampling_threshold_config(controller: jubilant.Juju):
    controller.config(
        "controller", {"workload-tracing-tail-sampling-threshold": "5ms"}
    )
    controller.wait(jubilant.all_active)

    config = controller.config("controller")
    assert config["workload-tracing-tail-sampling-threshold"] == "5ms"

    controller.config("controller", reset=["workload-tracing-tail-sampling-threshold"])
    controller.wait(jubilant.all_active)
