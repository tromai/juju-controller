"""Jubilant + pytest-jubilant port of `suites/controllercharm/prometheus.sh`.

Specifically, this ports the ``run_prometheus_cross_controller`` bash function.

Bash function being ported:

    run_prometheus_cross_controller() {
        CONTROLLER_MODEL_NAME="test-prometheus-cmr-ctrlr"
        bootstrap "${CONTROLLER_MODEL_NAME}" "${file}"     # ctrl on default cloud
        CONTROLLER_NAME=$(juju controllers --format json | yq -r '."current-controller"')

        K8S_CLOUD=${K8S_CLOUD:-microk8s}
        PROMETHEUS_MODEL_NAME="test-prometheus-cmr-prom"
        BOOTSTRAP_PROVIDER='k8s' BOOTSTRAP_CLOUD="${K8S_CLOUD}" \
            bootstrap "${PROMETHEUS_MODEL_NAME}" "${file}"  # 2nd controller on k8s

        juju offer -c "${CONTROLLER_NAME}" controller.controller:metrics-endpoint

        juju deploy prometheus-k8s --channel 1/stable --trust
        juju relate prometheus-k8s "${CONTROLLER_NAME}:controller.controller"
        wait_for "prometheus-k8s" "$(active_idle_condition "prometheus-k8s" 0)"
        retry 'check_prometheus_targets prometheus-k8s 0' 30

        juju remove-relation prometheus-k8s controller
        retry 'check_prometheus_no_target prometheus-k8s 0' 30
        juju status -m controller --format json | yq -r "$(active_condition "controller")"
        | check "controller"
        juju status --format json | yq -r "$(active_condition "prometheus-k8s")"
        | check "prometheus-k8s"

        juju remove-application prometheus-k8s --destroy-storage --no-prompt \
            --force --no-wait
        destroy_controller "${PROMETHEUS_MODEL_NAME}"
    }

The flow exercises **cross-controller relations**: the controller charm lives
on the source controller (reached via the ``controller`` fixture), and
prometheus-k8s lives on a pre-existing Kubernetes controller/model (reached
via the ``k8s_juju`` fixture -- see conftest.py for the
``JUJU_ITEST_K8S_MODEL`` env var that selects it). prometheus scrapes the
controller metrics from across the controller boundary.

The wait / active / scrape-target checks are expressed directly in terms of
Jubilant's primitives -- we only add custom logic where Jubilant genuinely
can't help (the Prometheus HTTP target check, which lives inside the
prometheus-k8s unit and isn't visible in `juju status`, and the cross-
controller offer/consume/integrate dance). Both live in `_helpers.py`,
shared with `test_prometheus.py` and `test_prometheus_multi.py`.

NOT bootstrapped here -- both controllers are assumed to already exist.

Run with::

    JUJU_ITEST_K8S_MODEL=ctrl-k8s:cos \
    pytest tests/integration/test_prometheus_cmr.py -v
"""

from __future__ import annotations

import jubilant
import pytest

import _helpers

# ---------------------------------------------------------------------------
# The ported test
# ---------------------------------------------------------------------------


OFFER_NAME = 'prom-targets'
CONSUMER_ALIAS = 'controller-targets'


@pytest.mark.prometheus
def test_run_prometheus_cross_controller(
    k8s_juju: jubilant.Juju,
    controller: jubilant.Juju,
) -> None:
    """Direct port of `run_prometheus_cross_controller` from prometheus.sh."""
    juju = k8s_juju

    # ---- Offer the controller charm's metrics-endpoint from the source
    # controller model, consume it on the k8s model, and integrate the
    # prometheus-k8s app. Equivalent to:
    #     juju offer -c "${CONTROLLER_NAME}" controller.controller:metrics-endpoint
    #     juju deploy prometheus-k8s --channel 1/stable --trust
    #     juju relate prometheus-k8s "${CONTROLLER_NAME}:controller.controller"
    juju.deploy('prometheus-k8s', channel='1/stable', trust=True)
    _helpers.cross_model_integrate(
        offerer=controller,
        offerer_app='controller',
        offerer_endpoint='metrics-endpoint',
        offer_name=OFFER_NAME,
        consumer=juju,
        consumer_app='prometheus-k8s',
        alias=CONSUMER_ALIAS,
    )

    try:
        # ---- Wait for prometheus-k8s/0 to be active+idle and for Prometheus
        # to have scraped the controller across the controller boundary.
        # Equivalent to:
        #     wait_for "prometheus-k8s" "$(active_idle_condition "prometheus-k8s" 0)"
        #     retry 'check_prometheus_targets prometheus-k8s 0' 30
        juju.wait(_helpers.is_unit_ready('prometheus-k8s'), error=jubilant.any_error)
        _helpers.wait_for_controller_target(juju, expected=True)

        # ---- Remove the cross-model relation. Equivalent to:
        #     juju remove-relation prometheus-k8s controller
        juju.remove_relation('prometheus-k8s', CONSUMER_ALIAS)

        # ---- Wait until Prometheus no longer scrapes the controller, and
        # check both apps are still active. Equivalent to:
        #     retry 'check_prometheus_no_target prometheus-k8s 0' 30
        #     juju status -m controller --format json | yq -r \
        #         "$(active_condition "controller")" | check "controller"
        #     juju status --format json | yq -r \
        #         "$(active_condition "prometheus-k8s")" | check "prometheus-k8s"
        _helpers.wait_for_controller_target(juju, expected=False)
        controller.wait(
            lambda s: jubilant.all_active(s, 'controller'),
            error=jubilant.any_error,
        )
        juju.wait(
            lambda s: jubilant.all_active(s, 'prometheus-k8s'),
            error=jubilant.any_error,
        )

        # ---- Remove prometheus-k8s with destroy-storage, no-wait, force.
        # Equivalent to:
        #     juju remove-application prometheus-k8s --destroy-storage \
        #         --no-prompt --force --no-wait
        # Juju.remove_application covers --destroy-storage/--no-prompt/--force
        # but not --no-wait, so we drop into Juju.cli for full parity with
        # the bash flags.
        juju.cli(
            'remove-application',
            'prometheus-k8s',
            '--destroy-storage',
            '--no-prompt',
            '--force',
            '--no-wait',
        )
    finally:
        # Best-effort cleanup of the cross-controller offer/consume/alias.
        _helpers.cross_model_teardown(
            offerer=controller,
            offer_name=OFFER_NAME,
            consumer=juju,
            consumer_app='prometheus-k8s',
            alias=CONSUMER_ALIAS,
        )
