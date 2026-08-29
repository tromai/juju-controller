"""Fixtures and helpers for Jubilant-based integration tests.

Unlike an earlier version of this file, these tests **assume a Juju
controller has already been bootstrapped** and is running this repo's
juju-controller charm in its `controller` model (see `test_config.py` /
`test_smoke.py` for the simplest examples: they just do
`jubilant.Juju(model="controller")` and go). Nothing here bootstraps or
destroys a controller -- do that yourself first, for example:

    charmcraft pack
    juju bootstrap lxd juju-controller-itest \\
        --controller-charm-path=./juju-controller_*.charm
    pip install jubilant pytest pyyaml
    pytest tests/integration -v

Some tests (`test_prometheus.py`) need a provider charm that only ships for
Kubernetes (`prometheus-k8s`). Those tests are cross-model/cross-controller
and are skipped unless you point them at an existing k8s controller/model
via the JUJU_ITEST_K8S_MODEL environment variable, for example:

    microk8s status --wait-ready
    juju bootstrap microk8s itest-k8s
    juju add-model cos
    export JUJU_ITEST_K8S_MODEL="itest-k8s:cos"
    pytest tests/integration -v
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable

import jubilant
import pytest


@pytest.fixture(scope="session")
def controller() -> jubilant.Juju:
    """Return a Juju client for the already-bootstrapped controller model.

    This assumes a Juju controller running this repo's juju-controller
    charm has already been bootstrapped (see the module docstring above) --
    it does not bootstrap or destroy anything itself.
    """
    return jubilant.Juju(model="controller")


@pytest.fixture(scope="session")
def k8s_juju() -> jubilant.Juju:
    """Return a Juju client for a pre-existing Kubernetes model.

    Used by tests that need a k8s-only COS charm (prometheus-k8s) related
    cross-model/cross-controller to the (machine-based) controller model.
    Skips if JUJU_ITEST_K8S_MODEL isn't set, since we can't safely bootstrap
    a whole second controller as a test fixture.
    """
    model = os.environ.get("JUJU_ITEST_K8S_MODEL")
    if not model:
        pytest.skip(
            "Set JUJU_ITEST_K8S_MODEL=<controller>:<model> (pointing at a microk8s "
            "controller/model) to run the cross-model COS tests."
        )
    return jubilant.Juju(model=model)


# --- Cross-model offer/consume/integrate helpers -----------------------------
#
# These mirror what `juju offer` / `juju consume` / `juju integrate` do across
# controllers, as shown in the README for relating juju-dashboard via a
# cross-model integration. They're split into separate offer/consume/integrate
# steps (rather than one do-it-all call) so that a single offer can be
# consumed once and then integrated with *multiple* local applications, which
# is what the upstream `run_prometheus_multiple_units` test does (one
# `juju offer`, two separate `juju relate`s to it).


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


def remove_cross_model_offer(*, offerer: jubilant.Juju, offer_name: str) -> None:
    """Best-effort removal of a cross-model offer."""
    try:
        model_info = offerer.show_model()
        offerer.cli(
            "remove-offer",
            f"admin/{model_info.short_name}.{offer_name}",
            "-y",
            include_model=False,
        )
    except jubilant.CLIError:
        pass


def cross_model_teardown(
    *,
    offerer: jubilant.Juju,
    offer_name: str,
    consumer: jubilant.Juju,
    consumer_app: str,
    alias: str,
) -> None:
    """Best-effort cleanup counterpart to `cross_model_integrate`."""
    try:
        consumer.remove_relation(consumer_app, alias)
    except jubilant.CLIError:
        pass
    try:
        consumer.remove_application(alias)
    except jubilant.CLIError:
        pass
    remove_cross_model_offer(offerer=offerer, offer_name=offer_name)


# --- Prometheus targets-API helpers ------------------------------------------
#
# These mirror the `get_juju_target` / `check_prometheus_targets` /
# `check_prometheus_no_target` bash functions in juju/juju's
# `tests/suites/controllercharm/prometheus.sh`: they talk to a Prometheus
# unit's HTTP API directly (there's no way to observe the effect of the
# controller charm's `add_metrics_user`/`MetricsEndpointProvider` calls
# purely through `juju status`).


def _prometheus_targets(address: str) -> list[dict]:
    """Fetch the list of active scrape targets from a Prometheus unit's HTTP API."""
    url = f"http://{address}:9090/api/v1/targets"
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
        data = json.load(resp)
    return data["data"]["activeTargets"]


def _find_target(address: str, app_name: str) -> dict | None:
    """Return the Prometheus scrape target for `app_name`, if present."""
    for target in _prometheus_targets(address):
        if target.get("labels", {}).get("juju_application") == app_name:
            return target
    return None


def retry(
    condition: Callable[[], bool],
    *,
    attempts: int = 30,
    delay: float = 2.0,
) -> None:
    """Call `condition()` repeatedly until it returns true.

    Mirrors the upstream `retry` bash helper (`retry '<command>' 30`) used
    throughout the juju/juju test suites.

    Raises AssertionError if `condition` never returns true within `attempts` tries.
    """
    for attempt in range(1, attempts + 1):
        if condition():
            return
        if attempt < attempts:
            time.sleep(delay)
    raise AssertionError(f"condition {condition!r} not met after {attempts} attempts")


def wait_for_prometheus_target_up(
    address: str, *, app_name: str = "controller", attempts: int = 30, delay: float = 2.0
) -> None:
    """Poll a Prometheus unit's targets API until `app_name` is an "up" scrape target.

    Equivalent of the upstream `retry 'check_prometheus_targets <app> <unit>' 30`.
    """

    def check() -> bool:
        target = _find_target(address, app_name)
        return target is not None and target.get("health") == "up"

    retry(check, attempts=attempts, delay=delay)


def wait_for_prometheus_target_gone(
    address: str, *, app_name: str = "controller", attempts: int = 30, delay: float = 2.0
) -> None:
    """Poll until `app_name` is no longer present in a Prometheus unit's scrape targets.

    Equivalent of the upstream `retry 'check_prometheus_no_target <app> <unit>' 30`.
    """
    retry(lambda: _find_target(address, app_name) is None, attempts=attempts, delay=delay)
