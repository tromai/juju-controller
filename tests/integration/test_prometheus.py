# Copyright 2026 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

"""Port of ``run_prometheus`` from juju/juju's ``tests/suites/controllercharm/prometheus.sh``.

Upstream (https://github.com/juju/juju/blob/main/tests/suites/controllercharm/prometheus.sh)::

    run_prometheus() {
        bootstrap "test-prometheus" "${file}"

        juju offer controller.controller:metrics-endpoint

        juju deploy prometheus-k8s --channel 1/stable --trust
        juju relate prometheus-k8s controller.controller
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
        destroy_controller "test-prometheus"
    }

Prometheus is deployed in a temporary model on the controller under test, so
(like upstream, which only runs this on the ``k8s`` provider) the test is
skipped unless that controller is on a Kubernetes cloud. Instead of a fresh
controller, the test uses a temporary model from pytest-jubilant's
``juju`` fixture (destroyed at module teardown), and a uniquely named offer
(see the ``metrics_offer`` fixture).
"""

from __future__ import annotations

import _helpers
import jubilant
import pytest

pytestmark = [pytest.mark.prometheus, pytest.mark.usefixtures("require_k8s_controller")]


def test_run_prometheus(juju: jubilant.Juju, controller: jubilant.Juju, metrics_offer: str):
    # juju deploy prometheus-k8s --channel 1/stable --trust
    # juju relate prometheus-k8s controller.controller
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
