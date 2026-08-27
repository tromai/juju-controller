"""Integration tests for the `metrics-endpoint` (prometheus_scrape) endpoint.

Requires JUJU_ITEST_K8S_MODEL to be set to a microk8s controller/model where
`prometheus-k8s` can be deployed; see conftest.py for details. Skips otherwise.
"""

from __future__ import annotations

import jubilant

import conftest


def test_metrics_endpoint_cross_model(controller: jubilant.Juju, k8s_juju: jubilant.Juju):
    k8s_juju.deploy("prometheus-k8s", channel="latest/stable", trust=True)
    k8s_juju.wait(lambda status: jubilant.all_active(status, "prometheus-k8s"))

    conftest.cross_model_integrate(
        offerer=k8s_juju,
        offerer_app="prometheus-k8s",
        offerer_endpoint="metrics-endpoint",
        offer_name="metrics",
        consumer=controller,
        consumer_app="controller",
        alias="prometheus",
    )
    controller.wait(jubilant.all_active)

    # The controller charm creates a metrics user via the control socket and
    # publishes the scrape job through MetricsEndpointProvider; the only
    # externally-observable evidence within reach of Jubilant is that both
    # sides settle to 'active' and the relation is visible in status.
    status = controller.status()
    assert any(
        rel.related_app == "prometheus"
        for rel in status.apps["controller"].relations.get("metrics-endpoint", [])
    )


def test_metrics_endpoint_removal(controller: jubilant.Juju, k8s_juju: jubilant.Juju):
    conftest.cross_model_teardown(
        offerer=k8s_juju,
        offer_name="metrics",
        consumer=controller,
        consumer_app="controller",
        alias="prometheus",
    )
    controller.wait(jubilant.all_active)
    k8s_juju.remove_application("prometheus-k8s")
