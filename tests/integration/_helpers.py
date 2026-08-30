"""Shared helpers for the Jubilant integration tests.

This logic was previously copy-pasted (with minor variations) into
``test_prometheus.py``, ``test_prometheus_multi.py``, and
``test_prometheus_cmr.py``. It's collected here as the single source of
truth; none of these are pytest fixtures, so this module is imported
directly (``import _helpers``) rather than picked up via ``conftest.py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import jubilant


def is_unit_ready(app_name: str, unit_index: int = 0) -> Callable[[jubilant.Status], bool]:
    """Return a `Juju.wait` predicate: True when `<app_name>/<unit_index>` is active+idle.

    Equivalent to the bash `active_idle_condition "<app>" <unit_index>` helper.
    """
    unit_name = f"{app_name}/{unit_index}"

    def predicate(status: jubilant.Status) -> bool:
        app = status.apps.get(app_name)
        if app is None:
            return False
        unit = app.units.get(unit_name)
        if unit is None:
            return False
        return unit.is_active and unit.juju_status.current == "idle"

    return predicate


def controller_target_present(
    juju: jubilant.Juju,
    expected: bool,
    *,
    prom_app: str = "prometheus-k8s",
    prom_unit_index: int = 0,
    controller_app: str = "controller",
) -> bool:
    """Equivalent to `check_prometheus_targets` / `check_prometheus_no_target`.

    Runs `curl http://localhost:9090/api/v1/targets` inside the Prometheus
    unit `<prom_app>/<prom_unit_index>` (via `Juju.exec`) and returns True
    iff a target with `juju_application == controller_app` and
    `health == "up"` is (or isn't, depending on *expected*) listed.

    Any error (unit not ready yet, curl failed, bad JSON, etc.) is treated as
    "not yet as expected" so the surrounding `Juju.wait` keeps polling.
    """
    unit_name = f"{prom_app}/{prom_unit_index}"
    try:
        task = juju.exec(
            "curl",
            "-sS",
            "-m",
            "2",
            "http://localhost:9090/api/v1/targets",
            unit=unit_name,
        )
    except (jubilant.TaskError, jubilant.CLIError, ValueError):
        return not expected

    try:
        payload: dict[str, Any] = json.loads(task.stdout)
    except json.JSONDecodeError:
        return not expected

    targets = payload.get("data", {}).get("activeTargets", []) or []
    has_target = any(_is_up_target(tgt, controller_app) for tgt in targets)
    return has_target == expected


def _is_up_target(target: dict[str, Any], controller_app: str) -> bool:
    is_controller = target.get("labels", {}).get("juju_application") == controller_app
    is_up = target.get("health") == "up"
    return is_controller and is_up


def wait_for_controller_target(
    juju: jubilant.Juju,
    expected: bool,
    *,
    prom_app: str = "prometheus-k8s",
    prom_unit_index: int = 0,
    controller_app: str = "controller",
    timeout: float = 5 * 60,
) -> None:
    """Equivalent to `retry 'check_prometheus_targets ...' 30` (and its inverse).

    Polls every `Juju.wait.delay` seconds until the assertion holds, with an
    overall timeout. Errors are swallowed inside `controller_target_present`
    so the loop keeps going while Prometheus is still starting up.
    """
    juju.wait(
        lambda _: controller_target_present(
            juju,
            expected,
            prom_app=prom_app,
            prom_unit_index=prom_unit_index,
            controller_app=controller_app,
        ),
        timeout=timeout,
        # successes>1 would require the assertion to hold several polls in a
        # row; we want to react to the first matching scrape so we keep the
        # default of 3 (the predicate must hold 3 polls in a row before wait
        # returns, which is the same "breathe" behaviour as bash wait_for).
    )


# --- Cross-model offer/consume/integrate helpers -----------------------------
#
# These mirror what `juju offer` / `juju consume` / `juju integrate` do across
# controllers, as shown in the README for relating juju-dashboard via a
# cross-model integration. Offer/consume are split out (rather than folded
# into one do-it-all call) so a single offer can be consumed once and then
# integrated with *multiple* local applications if needed.


def cross_model_offer(
    *, offerer: jubilant.Juju, offerer_app: str, offerer_endpoint: str, offer_name: str
) -> None:
    """Offer an endpoint from one controller/model for cross-model consumption."""
    offerer.offer(offerer_app, endpoint=offerer_endpoint, name=offer_name)


def cross_model_consume(
    *, offerer: jubilant.Juju, offer_name: str, consumer: jubilant.Juju, alias: str
) -> None:
    """Consume a previously-created offer into another controller/model."""
    model_info = offerer.show_model()
    consumer.consume(
        f"{model_info.short_name}.{offer_name}",
        alias,
        controller=model_info.controller_name,
        owner="admin",
    )


def cross_model_integrate(
    *,
    offerer: jubilant.Juju,
    offerer_app: str,
    offerer_endpoint: str,
    offer_name: str,
    consumer: jubilant.Juju,
    consumer_app: str,
    alias: str,
) -> None:
    """Offer an endpoint from one controller/model, consume it, and integrate it.

    Convenience wrapper around `cross_model_offer` + `cross_model_consume` +
    `Juju.integrate` for the common case of a single offerer and a single
    consuming application.
    """
    cross_model_offer(
        offerer=offerer,
        offerer_app=offerer_app,
        offerer_endpoint=offerer_endpoint,
        offer_name=offer_name,
    )
    cross_model_consume(offerer=offerer, offer_name=offer_name, consumer=consumer, alias=alias)
    consumer.integrate(consumer_app, alias)
