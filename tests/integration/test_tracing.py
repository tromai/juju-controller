"""Integration tests for the `charm-tracing` / `workload-tracing` endpoints.

Requires JUJU_ITEST_K8S_MODEL to be set to a microk8s controller/model where
`tempo-coordinator-k8s` and `self-signed-certificates` can be deployed; see
conftest.py for details. Skips otherwise.
"""

from __future__ import annotations

import jubilant

import conftest


def test_charm_tracing_config_written(controller: jubilant.Juju, k8s_juju: jubilant.Juju):
    k8s_juju.deploy("tempo-coordinator-k8s", channel="latest/edge", trust=True)
    k8s_juju.deploy("self-signed-certificates", channel="latest/stable")
    k8s_juju.integrate("tempo-coordinator-k8s", "self-signed-certificates")
    k8s_juju.wait(jubilant.all_active)

    conftest.cross_model_integrate(
        offerer=k8s_juju,
        offerer_app="tempo-coordinator-k8s",
        offerer_endpoint="tracing",
        offer_name="charm-tracing",
        consumer=controller,
        consumer_app="controller",
        alias="charm-tracing",
    )
    controller.wait(jubilant.all_active)

    # There's no relation-data proof of the internal control-socket call; the
    # only observable evidence is that controller.conf on the unit picked up
    # the tracing keys written via ControlSocketClient.set_charm_tracing_config.
    conf = controller.ssh(
        "controller/0",
        "sudo cat /var/lib/juju/agents/controller-*/controller.conf",
    )
    assert "tracing" in conf.lower()


def test_charm_tracing_removal(controller: jubilant.Juju, k8s_juju: jubilant.Juju):
    conftest.cross_model_teardown(
        offerer=k8s_juju,
        offer_name="charm-tracing",
        consumer=controller,
        consumer_app="controller",
        alias="charm-tracing",
    )
    controller.wait(jubilant.all_active)


def test_workload_tracing_config(controller: jubilant.Juju, k8s_juju: jubilant.Juju):
    conftest.cross_model_integrate(
        offerer=k8s_juju,
        offerer_app="tempo-coordinator-k8s",
        offerer_endpoint="tracing",
        offer_name="workload-tracing",
        consumer=controller,
        consumer_app="controller",
        alias="workload-tracing",
    )
    controller.wait(jubilant.all_active)

    conf = controller.ssh(
        "controller/0",
        "sudo cat /var/lib/juju/agents/controller-*/controller.conf",
    )
    assert "tracing" in conf.lower()

    conftest.cross_model_teardown(
        offerer=k8s_juju,
        offer_name="workload-tracing",
        consumer=controller,
        consumer_app="controller",
        alias="workload-tracing",
    )
    controller.wait(jubilant.all_active)
    k8s_juju.remove_application("tempo-coordinator-k8s")
    k8s_juju.remove_application("self-signed-certificates")


def test_workload_tracing_config_options(controller: jubilant.Juju):
    """Config validation for workload-tracing options (no relation required)."""
    controller.config(
        "controller",
        {
            "workload-tracing-sample-ratio": 0.5,
            "workload-tracing-stack-traces": True,
        },
    )
    controller.wait(jubilant.all_active)

    config = controller.config("controller")
    assert config["workload-tracing-sample-ratio"] == 0.5
    assert config["workload-tracing-stack-traces"] is True

    controller.config(
        "controller",
        reset=["workload-tracing-sample-ratio", "workload-tracing-stack-traces"],
    )
    controller.wait(jubilant.all_active)


def test_invalid_sample_ratio_blocks(controller: jubilant.Juju):
    """workload-tracing-sample-ratio outside [0, 1] should block the charm."""
    controller.config("controller", {"workload-tracing-sample-ratio": 2.0})
    controller.wait(
        lambda status: status.apps["controller"].app_status.current == "blocked"
    )

    controller.config("controller", reset=["workload-tracing-sample-ratio"])
    controller.wait(jubilant.all_active)
