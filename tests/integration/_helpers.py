# Copyright 2026 Canonical Ltd.
# Licensed under the GPLv3, see LICENSE file for details.

"""Shared helpers for the Jubilant integration tests.

These are the Python equivalents of the bash helpers used by the upstream
juju/juju ``tests/suites/controllercharm/prometheus.sh`` suite
(``wait_for``/``active_idle_condition``, ``check_controller_charm_active``,
``check_app_active``, ``check_prometheus_targets``,
``check_prometheus_no_target`` and ``get_juju_target``), expressed with
Jubilant's ``Juju.wait`` and status types.

None of these are pytest fixtures, so this module is imported directly
(``import _helpers``) rather than picked up via ``conftest.py``.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable
from typing import Any

import jubilant

logger = logging.getLogger(__name__)

CONTROLLER_APP = "controller"
PROMETHEUS_PORT = 9090

# Upstream waits for up to 600s (the `wait_for` default) for a freshly
# deployed or scaled Prometheus unit to settle.
DEPLOY_TIMEOUT = 10 * 60
# Upstream retries the Prometheus target checks 30 times, 5s apart, with a
# probe that can itself take up to 10s.
TARGET_TIMEOUT = 5 * 60
# Upstream retries the "still active" checks 10 times, 5s apart, as relation
# teardown hooks may still be settling.
SETTLE_TIMEOUT = 3 * 60
# Delay between status polls; matches the default `retry` delay upstream.
POLL_DELAY = 5


def unit_active_idle(app: str, unit_index: int = 0) -> Callable[[jubilant.Status], bool]:
    """Return a `Juju.wait` predicate: True when ``<app>/<unit_index>`` is active and idle.

    Equivalent to upstream's ``wait_for <app> "$(active_idle_condition <app> <index>)"``.
    Jubilant's ``all_active``/``all_agents_idle`` look at every unit of an app,
    so they would return early while a newly added unit isn't in the status
    yet; this checks one specific unit instead.
    """

    def ready(status: jubilant.Status) -> bool:
        app_status = status.apps.get(app)
        unit = app_status.units.get(f"{app}/{unit_index}") if app_status else None
        return unit is not None and unit.is_active and unit.juju_status.current == "idle"

    ready.__qualname__ = f"unit_active_idle({app!r}, {unit_index})"
    return ready


def wait_controller_active(controller: jubilant.Juju, *, timeout: float = SETTLE_TIMEOUT) -> None:
    """Wait for the controller charm to be active, failing fast if it goes into error.

    Equivalent to upstream's ``retry 'check_controller_charm_active' 10``. Like
    upstream, dump the controller model's status and recent logs on failure, so
    a failed check states which hook put the unit in error, and not only that
    the charm stopped being active.
    """
    try:
        controller.wait(
            lambda status: jubilant.all_active(status, CONTROLLER_APP),
            error=lambda status: jubilant.any_error(status, CONTROLLER_APP),
            delay=POLL_DELAY,
            timeout=timeout,
        )
    except (TimeoutError, jubilant.WaitError):
        logger.error("==> controller charm not active")
        try:
            logger.error("juju status:\n%s", controller.cli("status", "--format", "yaml"))
            logger.error("juju debug-log:\n%s", controller.debug_log(limit=100))
        except jubilant.CLIError as e:
            logger.error("Failed to collect controller diagnostics: %s", e.stderr)
        raise


def wait_app_active(juju: jubilant.Juju, app: str, *, timeout: float = SETTLE_TIMEOUT) -> None:
    """Wait for *app* to be active.

    Equivalent to upstream's ``retry 'check_app_active <app>' 10`` and
    ``wait_for <app> "$(active_condition <app>)"``.
    """
    juju.wait(lambda status: jubilant.all_active(status, app), delay=POLL_DELAY, timeout=timeout)


def wait_for_controller_target(
    juju: jubilant.Juju,
    prom_app: str,
    unit_index: int = 0,
    *,
    present: bool = True,
    timeout: float = TARGET_TIMEOUT,
) -> None:
    """Wait until Prometheus does (or doesn't) list the controller as a scrape target.

    Equivalent to upstream's ``retry 'check_prometheus_targets <app> <unit>' 30``
    (``present=True``: a controller target exists and every controller target
    is "up") and ``retry 'check_prometheus_no_target <app> <unit>' 30``
    (``present=False``: no controller target exists).

    An unresolvable unit address or an unreachable Prometheus API never counts
    as success, so a down Prometheus can't pass the ``present=False`` check.
    """

    def ready(status: jubilant.Status) -> bool:
        try:
            targets = get_controller_targets(status, prom_app, unit_index)
        except PrometheusProbeError as e:
            logger.info("%s", e)
            return False

        if not present:
            if targets:
                logger.info("Whoops: Juju controller still found in Prometheus targets")
                return False
            logger.info("Success: Juju controller removed from Prometheus targets")
            return True

        if not targets:
            logger.info("Juju controller not found in Prometheus targets")
            return False
        for target in targets:
            if target.get("health") != "up":
                logger.info(
                    "Controller metrics endpoint status: %s: %s",
                    target.get("health"),
                    target.get("lastError"),
                )
                return False
        logger.info("Controller metrics endpoint is up")
        return True

    ready.__qualname__ = f"controller_target_{'present' if present else 'absent'}"
    # One positive probe is enough, like upstream's `retry`; the probe itself
    # queries Prometheus, so requiring several stable statuses adds nothing.
    juju.wait(ready, delay=POLL_DELAY, timeout=timeout, successes=1)


class PrometheusProbeError(Exception):
    """Raised when the Prometheus targets API of a unit can't be queried."""


def get_controller_targets(
    status: jubilant.Status, prom_app: str, unit_index: int = 0
) -> list[dict[str, Any]]:
    """Return the controller's active scrape targets, as seen by ``<prom_app>/<unit_index>``.

    Equivalent to upstream's ``get_juju_target``: read the unit's address from
    the status, query ``http://<address>:9090/api/v1/targets`` from the test
    host (once: the caller's `Juju.wait` loop provides the retries), and keep
    the targets whose ``juju_application`` label is the controller app.

    Raises:
        PrometheusProbeError: if the unit's address can't be resolved, or the
            Prometheus API can't be reached or returns garbage.
    """
    unit_name = f"{prom_app}/{unit_index}"
    app_status = status.apps.get(prom_app)
    unit = app_status.units.get(unit_name) if app_status else None
    address = unit.address if unit else ""
    if not address:
        raise PrometheusProbeError(f"could not resolve {unit_name} address")

    url = f"http://{address}:{PROMETHEUS_PORT}/api/v1/targets"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.load(response)
    except (OSError, ValueError) as e:
        # URLError and timeouts are OSErrors; JSONDecodeError is a ValueError.
        raise PrometheusProbeError(
            f"Prometheus API at {address}:{PROMETHEUS_PORT} unreachable: {e}"
        ) from e

    targets = (payload.get("data") or {}).get("activeTargets") or []
    return [
        t for t in targets if (t.get("labels") or {}).get("juju_application") == CONTROLLER_APP
    ]


def remove_application_no_wait(juju: jubilant.Juju, *apps: str) -> None:
    """Remove *apps* the way upstream does, with ``--force --no-wait``.

    That is, ``juju remove-application <app> --destroy-storage --no-prompt
    --force --no-wait``. `Juju.remove_application` has no ``--no-wait``
    option, hence the raw CLI call. Upstream notes these flags are a
    workaround until a storage bug is fixed; the model is destroyed by
    pytest-jubilant afterwards anyway.
    """
    for app in apps:
        juju.cli(
            "remove-application", app, "--destroy-storage", "--no-prompt", "--force", "--no-wait"
        )
