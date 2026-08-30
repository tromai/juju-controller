"""Jubilant + pytest-jubilant port of `suites/controllercharm/prometheus.sh`.

Specifically, this ports the ``run_prometheus_multiple_units`` bash function.

Bash function being ported:

    run_prometheus_multiple_units() {
        MODEL_NAME="test-prometheus-multi"
        bootstrap "${MODEL_NAME}" "${file}"        # fresh controller + model

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
        juju status -m controller --format json | yq -r "$(active_condition "controller")"
        | check "controller"
        juju status --format json | yq -r "$(active_condition "p1" 0)" | check "p1"

        juju remove-relation p2 controller
        # Wait until the application p2 settles before health checks
        wait_for "p2" "$(active_condition "p2" 1)"

        # Check Juju controller is removed from Prometheus targets
        retry 'check_prometheus_no_target p2 0' 30
        # Check no errors in controller charm or Prometheus
        juju status -m controller --format json | yq -r "$(active_condition "controller")"
        | check "controller"
        juju status --format json | yq -r "$(active_condition "p2" 1)" | check "p2"

        juju remove-relation p1 controller

        # Check Juju controller is removed from Prometheus targets
        retry 'check_prometheus_no_target p1 0' 30
        # Check no errors in controller charm or Prometheus
        juju status -m controller --format json | yq -r "$(active_condition "controller")"
        | check "controller"
        # Ensure p1 is still healty
        wait_for "p1" "$(active_condition "p1" 0)"

        juju remove-application p1 --destroy-storage --no-prompt --force --no-wait
        juju remove-application p2 --destroy-storage --no-prompt --force --no-wait
        destroy_controller "${MODEL_NAME}"
    }

The flow exercises the controller charm with **multiple Prometheus relations**
on the same controller/model: deploy `p1`, deploy `p2`, scale `p1` to a
second unit, scale `p1` back, then tear down one relation at a time and
verify the controller app + prometheus apps stay healthy throughout.

The wait / active / scrape-target checks are expressed directly in terms of
Jubilant's primitives -- we only add custom logic where Jubilant genuinely
can't help (the Prometheus HTTP target check, which lives inside the
prometheus-k8s unit and isn't visible in `juju status`).

NOT bootstrapped here -- the conftest's ``juju_factory`` fixture creates and
destroys the temp model automatically, and the controller is left untouched.
The ``controller`` fixture (provided by the conftest) gives us a Juju handle
on the already-running controller model.

Run with::

    pytest tests/integration/test_prometheus_multi.py -v

Shared helpers (Prometheus targets-API polling, etc.) live in `_helpers.py`.
"""

from __future__ import annotations

import jubilant
import pytest
import pytest_jubilant

import _helpers


# ---------------------------------------------------------------------------
# Temp model fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def multi_model(juju_factory: pytest_jubilant.JujuFactory) -> jubilant.Juju:
    """Temp model on the existing k8s controller; torn down by pytest-jubilant."""
    return juju_factory.get_juju(suffix='prometheus-multi')


# ---------------------------------------------------------------------------
# The ported test
# ---------------------------------------------------------------------------


@pytest.mark.prometheus
def test_run_prometheus_multiple_units(
    multi_model: jubilant.Juju,
    controller: jubilant.Juju,
) -> None:
    """Direct port of `run_prometheus_multiple_units` from prometheus.sh."""
    juju = multi_model

    # ---- Offer the controller charm's metrics-endpoint. Equivalent to:
    #     juju offer controller.controller:metrics-endpoint
    juju.offer('controller.controller', endpoint='metrics-endpoint')

    # ---- Deploy p1 and p2, each related to the controller offer. Equivalent
    # to:
    #     juju deploy prometheus-k8s --channel 1/stable p1 --trust
    #     juju relate p1 controller.controller
    #     juju deploy prometheus-k8s --channel 1/stable p2 --trust
    #     juju relate p2 controller.controller
    juju.deploy('prometheus-k8s', 'p1', channel='1/stable', trust=True)
    juju.integrate('p1', 'controller.controller')
    juju.deploy('prometheus-k8s', 'p2', channel='1/stable', trust=True)
    juju.integrate('p2', 'controller.controller')

    # ---- Wait for p1/0 and p2/0 to be active+idle and for Prometheus to have
    # scraped the controller. Equivalent to:
    #     wait_for "p1" "$(active_idle_condition "p1" 0)"
    #     retry 'check_prometheus_targets p1 0' 30
    #     wait_for "p2" "$(active_idle_condition "p2" 0)"
    #     retry 'check_prometheus_targets p2 0' 30
    juju.wait(_helpers.is_unit_ready('p1', 0), error=jubilant.any_error)
    _helpers.wait_for_controller_target(juju, expected=True, prom_app='p1', prom_unit_index=0)

    juju.wait(_helpers.is_unit_ready('p2', 0), error=jubilant.any_error)
    _helpers.wait_for_controller_target(juju, expected=True, prom_app='p2', prom_unit_index=0)

    # ---- Scale p1 to a second unit and wait for it. Equivalent to:
    #     juju add-unit p1
    #     wait_for "p1" "$(active_idle_condition "p1" 1)"
    #     retry 'check_prometheus_targets p1 1' 30
    juju.add_unit('p1')
    juju.wait(_helpers.is_unit_ready('p1', 1), error=jubilant.any_error)
    _helpers.wait_for_controller_target(juju, expected=True, prom_app='p1', prom_unit_index=1)

    # ---- Scale p1 back to one unit. Equivalent to:
    #     juju remove-unit p1 --num-units 1
    #     wait_for "p1" "$(active_condition "p1" 0)"
    juju.remove_unit('p1', num_units=1)
    juju.wait(lambda s: jubilant.all_active(s, 'p1'), error=jubilant.any_error)

    # ---- Health-check controller charm and p1 are still active. Equivalent
    # to:
    #     juju status -m controller --format json | yq -r \
    #         "$(active_condition "controller")" | check "controller"
    #     juju status --format json | yq -r \
    #         "$(active_condition "p1" 0)" | check "p1"
    controller.wait(
        lambda s: jubilant.all_active(s, 'controller'),
        error=jubilant.any_error,
    )
    juju.wait(lambda s: jubilant.all_active(s, 'p1'), error=jubilant.any_error)

    # ---- Remove p2's relation and verify it stops scraping. Equivalent to:
    #     juju remove-relation p2 controller
    #     wait_for "p2" "$(active_condition "p2" 1)"
    #     retry 'check_prometheus_no_target p2 0' 30
    #     juju status -m controller --format json | yq -r \
    #         "$(active_condition "controller")" | check "controller"
    #     juju status --format json | yq -r \
    #         "$(active_condition "p2" 1)" | check "p2"
    juju.remove_relation('p2', 'controller')
    juju.wait(lambda s: jubilant.all_active(s, 'p2'), error=jubilant.any_error)
    _helpers.wait_for_controller_target(juju, expected=False, prom_app='p2', prom_unit_index=0)
    controller.wait(
        lambda s: jubilant.all_active(s, 'controller'),
        error=jubilant.any_error,
    )

    # ---- Remove p1's relation and verify it stops scraping. Equivalent to:
    #     juju remove-relation p1 controller
    #     retry 'check_prometheus_no_target p1 0' 30
    #     juju status -m controller --format json | yq -r \
    #         "$(active_condition "controller")" | check "controller"
    #     wait_for "p1" "$(active_condition "p1" 0)"
    juju.remove_relation('p1', 'controller')
    _helpers.wait_for_controller_target(juju, expected=False, prom_app='p1', prom_unit_index=0)
    controller.wait(
        lambda s: jubilant.all_active(s, 'controller'),
        error=jubilant.any_error,
    )
    juju.wait(lambda s: jubilant.all_active(s, 'p1'), error=jubilant.any_error)

    # ---- Remove both prometheus-k8s apps. Equivalent to:
    #     juju remove-application p1 --destroy-storage --no-prompt --force --no-wait
    #     juju remove-application p2 --destroy-storage --no-prompt --force --no-wait
    for app in ('p1', 'p2'):
        juju.cli(
            'remove-application',
            app,
            '--destroy-storage',
            '--no-prompt',
            '--force',
            '--no-wait',
        )
    # The temp model teardown happens in pytest-jubilant's `juju_factory`
    # fixture. The controller itself is left untouched.
