"""Integration tests for the `loki-push-api` endpoint.

Requires JUJU_ITEST_K8S_MODEL to be set to a microk8s controller/model where
`loki-k8s` can be deployed; see conftest.py for details. Skips otherwise.
"""

from __future__ import annotations

import jubilant

import conftest


def test_loki_endpoint_applied(controller: jubilant.Juju, k8s_juju: jubilant.Juju):
    k8s_juju.deploy("loki-k8s", channel="latest/stable", trust=True)
    k8s_juju.wait(lambda status: jubilant.all_active(status, "loki-k8s"))

    conftest.cross_model_integrate(
        offerer=k8s_juju,
        offerer_app="loki-k8s",
        offerer_endpoint="logging",
        offer_name="loki-push-api",
        consumer=controller,
        consumer_app="controller",
        alias="loki",
    )
    controller.wait(jubilant.all_active, timeout=600)

    status = controller.status()
    assert status.apps["controller"].app_status.current == "active"


def test_loki_insecure_skip_verify_config(controller: jubilant.Juju):
    """loki-insecure-skip-verify / loki-org-id are plain config, no relation needed."""
    controller.config(
        "controller",
        {"loki-insecure-skip-verify": True, "loki-org-id": "itest-org"},
    )
    controller.wait(jubilant.all_active)

    config = controller.config("controller")
    assert config["loki-insecure-skip-verify"] is True
    assert config["loki-org-id"] == "itest-org"

    controller.config("controller", reset=["loki-insecure-skip-verify", "loki-org-id"])
    controller.wait(jubilant.all_active)


def test_loki_endpoint_removed(controller: jubilant.Juju, k8s_juju: jubilant.Juju):
    conftest.cross_model_teardown(
        offerer=k8s_juju,
        offer_name="loki-push-api",
        consumer=controller,
        consumer_app="controller",
        alias="loki",
    )
    controller.wait(jubilant.all_active)
    k8s_juju.remove_application("loki-k8s")
