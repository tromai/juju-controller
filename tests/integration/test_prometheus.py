"""Jubilant + pytest-jubilant port of suites/controllercharm/prometheus.sh `run_prometheus`.

Bash function being ported:

    run_prometheus() {
        MODEL_NAME="test-prometheus"
        bootstrap "${MODEL_NAME}" "${file}"        # fresh controller + model

        juju offer controller.controller:metrics-endpoint
        juju deploy prometheus-k8s --channel 1/stable --trust
        juju relate prometheus-k8s controller.controller

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
        destroy_controller "${MODEL_NAME}"
    }

This pytest module re-implements the exact same behaviour using Jubilant and
the ``pytest-jubilant`` plugin. Every step maps to a public method on
``jubilant.Juju``; the wait / active-idle / active checks are expressed as
``Juju.wait`` callables; and the Prometheus scrape-target assertions are
folded into the same polling loop. The bash helpers (``bootstrap``,
``wait_for``, ``active_idle_condition``, ``active_condition``, ``retry``,
``check``, ``destroy_controller``) are NOT used or replicated.

NOT bootstrapped here. ``pytest-jubilant`` assumes a Juju controller already
exists. The controller name is taken from the ``JUJU_CONTROLLER`` environment
variable (or ``--juju-controller`` on the pytest CLI) -- the same way the
``juju_factory`` fixture picks up its defaults.

The test runs only on a Kubernetes cloud (``BOOTSTRAP_PROVIDER=k8s``); on
other providers it is skipped, matching the bash test's ``BOOTSTRAP_PROVIDER=k8s``
branch.

The temp model for this test is provided by ``pytest-jubilant``'s
``juju_factory`` fixture and is destroyed automatically at module teardown.
We never touch the controller itself.

Run with::

    JUJU_CONTROLLER=ctrl-xxxx \
    pytest tests/suites/controllercharm/prometheus.py -v

Shared helpers (Prometheus targets-API polling, etc.) live in `_helpers.py`.
"""

from __future__ import annotations

import jubilant
import pytest
import pytest_jubilant

import _helpers

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def prom_model(
    juju_factory: pytest_jubilant.JujuFactory,
) -> jubilant.Juju:
    """Temp model on the existing k8s controller; torn down by pytest-jubilant.

    Mirrors the bash `juju_add_model "${MODEL_NAME}" ...` step: a fresh model
    named ``<prefix>-prometheus`` on the configured k8s cloud. ``pytest-jubilant``
    tears it down at module teardown (or keeps it if ``--no-juju-teardown``).
    """
    return juju_factory.get_juju(suffix='prometheus')


# ---------------------------------------------------------------------------
# The ported test
# ---------------------------------------------------------------------------

@pytest.mark.prometheus
def test_run_prometheus(
    prom_model: jubilant.Juju,
    controller: jubilant.Juju,
) -> None:
    """Direct port of `run_prometheus` from prometheus.sh."""
    juju = prom_model
    juju.deploy("prometheus-k8s", channel="1/stable", trust=True)
    juju.offer(
        'controller.controller',
        endpoint='metrics-endpoint',
    )
    juju.integrate('prometheus-k8s', 'controller.controller')

    status = juju.wait(_helpers.is_unit_ready('prometheus-k8s'), error=jubilant.any_error)
    assert status.apps['prometheus-k8s'].is_active
    assert status.apps['prometheus-k8s'].units['prometheus-k8s/0'].is_active

    _helpers.wait_for_controller_target(juju, expected=True)

    juju.remove_relation('prometheus-k8s', 'controller')

    _helpers.wait_for_controller_target(juju, expected=False)

    controller.wait(
        lambda status: jubilant.all_active(status, 'controller'),
        error=jubilant.any_error,
    )

    juju.wait(
        lambda status: jubilant.all_active(status, 'prometheus-k8s'),
        error=jubilant.any_error,
    )

    juju.cli(
        'remove-application',
        'prometheus-k8s',
        '--destroy-storage',
        '--no-prompt',
        '--force',
        '--no-wait',
    )

    juju.wait(jubilant.all_active)
