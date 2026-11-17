# Copyright 2026 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

"""Port of ``run_prometheus_cross_controller`` from juju/juju's ``controllercharm/prometheus.sh``.

Upstream (https://github.com/juju/juju/blob/main/tests/suites/controllercharm/prometheus.sh)::

    run_prometheus_cross_controller() {
        bootstrap "test-prometheus-cmr-ctrlr" "${file}"
        CONTROLLER_NAME=$(juju controllers --format json | yq -r '."current-controller"')

        # Prometheus must be deployed on k8s. By default, we choose microk8s, but you
        # can set the K8S_CLOUD environment variable to select a different cluster.
        K8S_CLOUD=${K8S_CLOUD:-microk8s}
        BOOTSTRAP_PROVIDER='k8s' BOOTSTRAP_CLOUD="${K8S_CLOUD}" \\
            bootstrap "test-prometheus-cmr-prom" "${file}"

        juju offer -c "${CONTROLLER_NAME}" controller.controller:metrics-endpoint

        juju deploy prometheus-k8s --channel 1/stable --trust
        juju relate prometheus-k8s "${CONTROLLER_NAME}:controller.controller"
        wait_for "prometheus-k8s" "$(active_idle_condition "prometheus-k8s" 0)"
        retry 'check_prometheus_targets prometheus-k8s 0' 30

        juju remove-relation prometheus-k8s controller
        # Check Juju controller is removed from Prometheus targets
        retry 'check_prometheus_no_target prometheus-k8s 0' 30
        # Check no errors in controller charm or Prometheus
        retry 'check_controller_charm_active' 10
        retry 'check_app_active prometheus-k8s' 10

        juju remove-application prometheus-k8s --destroy-storage --no-prompt \\
            --force --no-wait # TODO: remove these flags once storage bug is fixed
        destroy_controller "test-prometheus-cmr-prom"
    }

This exercises a cross-controller relation: the controller charm lives on
the controller under test (any cloud), and prometheus-k8s lives in a
temporary model on a second, pre-existing controller on a Kubernetes cloud,
passed with ``--k8s-controller`` (the equivalent of upstream's
``K8S_CLOUD``). The test is skipped if that option isn't set. The temporary
model is created and destroyed by pytest-jubilant's ``juju_factory``, using
its per-model ``controller`` override.
"""

from __future__ import annotations

import _helpers
import jubilant
import pytest
import pytest_jubilant

pytestmark = pytest.mark.prometheus


@pytest.fixture(scope="module")
def juju(juju_factory: pytest_jubilant.JujuFactory, k8s_controller: str) -> jubilant.Juju:
    """Temporary model for prometheus-k8s on the ``--k8s-controller`` controller."""
    # Overrides pytest-jubilant's `juju` fixture, which uses --juju-controller.
    return juju_factory.get_juju("", controller=k8s_controller)


def test_run_prometheus_cross_controller(
    juju: jubilant.Juju, controller: jubilant.Juju, metrics_offer: str
):
    # juju deploy prometheus-k8s --channel 1/stable --trust
    # juju relate prometheus-k8s "${CONTROLLER_NAME}:controller.controller"
    juju.deploy("prometheus-k8s", channel="1/stable", trust=True)
    juju.consume(metrics_offer, "controller")
    juju.integrate("prometheus-k8s", "controller")

    juju.wait(_helpers.unit_active_idle("prometheus-k8s", 0), timeout=_helpers.DEPLOY_TIMEOUT)
    _helpers.wait_for_controller_target(juju, "prometheus-k8s", 0)

    juju.remove_relation("prometheus-k8s", "controller")
    _helpers.wait_for_controller_target(juju, "prometheus-k8s", 0, present=False)
    _helpers.wait_controller_active(controller)
    _helpers.wait_app_active(juju, "prometheus-k8s")

    _helpers.remove_application_no_wait(juju, "prometheus-k8s")
