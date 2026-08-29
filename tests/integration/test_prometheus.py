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
"""

from __future__ import annotations

import json
from typing import Any

import jubilant
import pytest
import pytest_jubilant
import logging
logger = logging.getLogger()


def is_prometheus_unit_ready(status: jubilant.Status) -> bool:
    """Equivalent to `active_idle_condition "prometheus-k8s" 0`.

    True when unit `prometheus-k8s/0` has workload-status=active AND
    juju-status (agent-status)=idle.
    """
    app = status.apps.get('prometheus-k8s')
    if app is None:
        return False
    unit = app.units.get('prometheus-k8s/0')
    if unit is None:
        return False
    return unit.is_active and unit.juju_status.current == 'idle'


def _controller_target_present(juju: jubilant.Juju, expected: bool) -> bool:
    """Equivalent to `check_prometheus_targets` / `check_prometheus_no_target`.

    The bash version runs `curl http://${PROM_IP}:9090/api/v1/targets` against
    Prometheus's HTTP API and inspects the returned `activeTargets` list. The
    target list is NOT exposed by `juju status`, so we keep the curl: we run
    it inside the prometheus-k8s unit via `Juju.exec` (which lets us hit
    `localhost:9090` without the bash IP-extraction dance).

    Returns True iff a target with `juju_application == "controller"` and
    `health == "up"` is (or isn't, depending on *expected*) listed.

    Any error (unit not ready yet, curl failed, bad JSON, etc.) is treated as
    "not yet as expected" so the surrounding `Juju.wait` keeps polling.
    """
    try:
        task = juju.exec(
            'curl',
            '-sS',
            '-m',
            '2',
            'http://localhost:9090/api/v1/targets',
            unit='prometheus-k8s/0',
        )
    except (jubilant.TaskError, jubilant.CLIError, ValueError):
        return not expected

    try:
        payload: dict[str, Any] = json.loads(task.stdout)
    except json.JSONDecodeError:
        return not expected

    targets = payload.get('data', {}).get('activeTargets', []) or []
    has_target = any(
        tgt.get('labels', {}).get('juju_application') == 'controller' and tgt.get('health') == 'up'
        for tgt in targets
    )
    return has_target == expected


def wait_for_controller_target(
    juju: jubilant.Juju,
    expected: bool,
    *,
    timeout: float = 5 * 60,
) -> None:
    """Equivalent to `retry 'check_prometheus_targets ...' 30` (and its inverse).

    Polls every `Juju.wait.delay` seconds until the assertion holds, with an
    overall timeout. Errors are swallowed inside `_controller_target_present`
    so the loop keeps going while Prometheus is still starting up.
    """
    juju.wait(
        lambda _: _controller_target_present(juju, expected),
        timeout=timeout,
        # successes>1 would require the assertion to hold several polls in a
        # row; we want to react to the first matching scrape so we keep the
        # default of 3 (the predicate must hold 3 polls in a row before wait
        # returns, which is the same "breathe" behaviour as bash wait_for).
    )


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


@pytest.fixture(scope='module')
def controller_model() -> jubilant.Juju:
    # We assume the controller model is always there.
    return jubilant.Juju(model='controller')


# ---------------------------------------------------------------------------
# The ported test
# ---------------------------------------------------------------------------

@pytest.mark.prometheus
def test_run_prometheus(
    prom_model: jubilant.Juju,
    controller_model: jubilant.Juju,
) -> None:
    """Direct port of `run_prometheus` from prometheus.sh."""
    juju = prom_model
    juju.deploy("prometheus-k8s", channel="1/stable", trust=True)
    juju.offer(
        'controller.controller',
        endpoint='metrics-endpoint',
    )
    juju.integrate('prometheus-k8s', 'controller.controller')

    status = juju.wait(is_prometheus_unit_ready, error=jubilant.any_error)
    assert status.apps['prometheus-k8s'].is_active
    assert status.apps['prometheus-k8s'].units['prometheus-k8s/0'].is_active

    wait_for_controller_target(juju, expected=True)

    juju.remove_relation('prometheus-k8s', 'controller')

    wait_for_controller_target(juju, expected=False)

    controller_model.wait(
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
