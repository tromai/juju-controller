# Copyright 2026 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

"""Port of ``run_prometheus_multiple_units`` from juju/juju's ``controllercharm/prometheus.sh``.

Checks the controller charm can handle multiple Prometheus relations.

Upstream (https://github.com/juju/juju/blob/main/tests/suites/controllercharm/prometheus.sh)::

    run_prometheus_multiple_units() {
        bootstrap "test-prometheus-multi" "${file}"

        juju offer controller.controller:metrics-endpoint

        juju deploy prometheus-k8s --channel 1/stable p1 --trust
        juju relate p1 controller.controller
        wait_for "p1" "$(active_idle_condition "p1" 0)"
        retry 'check_prometheus_targets p1 0' 30

        juju deploy prometheus-k8s --channel 1/stable p2 --trust
        juju relate p2 controller.controller
        wait_for "p2" "$(active_idle_condition "p2" 0)"
        retry 'check_prometheus_targets p2 0' 30

        juju add-unit p1
        wait_for "p1" "$(active_idle_condition "p1" 1)"
        retry 'check_prometheus_targets p1 1' 30

        juju remove-unit p1 --num-units 1
        # Wait until the application p1 settles before health checks
        wait_for "p1" "$(active_condition "p1" 0)"

        # Check all applications are still healthy
        retry 'check_controller_charm_active' 10
        retry 'check_app_active p1 0' 10

        juju remove-relation p2 controller
        # Wait until the application p2 settles before health checks
        wait_for "p2" "$(active_condition "p2" 1)"

        # Check Juju controller is removed from Prometheus targets
        retry 'check_prometheus_no_target p2 0' 30
        # Check no errors in controller charm or Prometheus
        retry 'check_controller_charm_active' 10
        retry 'check_app_active p2 1' 10

        juju remove-relation p1 controller

        # Check Juju controller is removed from Prometheus targets
        retry 'check_prometheus_no_target p1 0' 30
        # Check no errors in controller charm or Prometheus
        retry 'check_controller_charm_active' 10
        # Ensure p1 is still healty
        wait_for "p1" "$(active_condition "p1" 0)"

        juju remove-application p1 --destroy-storage --no-prompt \\
            --force --no-wait # TODO: remove these flags once storage bug is fixed
        juju remove-application p2 --destroy-storage --no-prompt \\
            --force --no-wait # TODO: remove these flags once storage bug is fixed
        destroy_controller "test-prometheus-multi"
    }

Note that the index in upstream's ``active_condition <app> <index>`` selects
an application (not a unit), so it's simply "<app> is active" here.

Like ``test_prometheus.py``, this only runs when the controller under test is
on a Kubernetes cloud, and uses a temporary model and a unique offer instead
of a fresh controller.
"""

from __future__ import annotations

import _helpers
import jubilant
import pytest

pytestmark = [pytest.mark.prometheus, pytest.mark.usefixtures("require_k8s_controller")]


def test_run_prometheus_multiple_units(
    juju: jubilant.Juju, controller: jubilant.Juju, metrics_offer: str
):
    juju.consume(metrics_offer, "controller")

    for app in ("p1", "p2"):
        juju.deploy("prometheus-k8s", app, channel="1/stable", trust=True)
        juju.integrate(app, "controller")
        juju.wait(_helpers.unit_active_idle(app, 0), timeout=_helpers.DEPLOY_TIMEOUT)
        _helpers.wait_for_controller_target(juju, app, 0)

    juju.add_unit("p1")
    juju.wait(_helpers.unit_active_idle("p1", 1), timeout=_helpers.DEPLOY_TIMEOUT)
    _helpers.wait_for_controller_target(juju, "p1", 1)

    # On Kubernetes models, remove-unit takes the app name and a unit count.
    juju.remove_unit("p1", num_units=1)
    # Wait until the application p1 settles before health checks.
    _helpers.wait_app_active(juju, "p1", timeout=_helpers.DEPLOY_TIMEOUT)
    # Check all applications are still healthy.
    _helpers.wait_controller_active(controller)
    _helpers.wait_app_active(juju, "p1")

    juju.remove_relation("p2", "controller")
    # Wait until the application p2 settles before health checks.
    _helpers.wait_app_active(juju, "p2", timeout=_helpers.DEPLOY_TIMEOUT)
    # Check Juju controller is removed from Prometheus targets.
    _helpers.wait_for_controller_target(juju, "p2", 0, present=False)
    # Check no errors in controller charm or Prometheus.
    _helpers.wait_controller_active(controller)
    _helpers.wait_app_active(juju, "p2")

    juju.remove_relation("p1", "controller")
    # Check Juju controller is removed from Prometheus targets.
    _helpers.wait_for_controller_target(juju, "p1", 0, present=False)
    # Check no errors in controller charm, and that p1 is still healthy.
    _helpers.wait_controller_active(controller)
    _helpers.wait_app_active(juju, "p1", timeout=_helpers.DEPLOY_TIMEOUT)

    _helpers.remove_application_no_wait(juju, "p1", "p2")
