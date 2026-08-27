"""Integration tests for the `s3-backend` endpoint.

`s3-integrator` is a machine charm, so this can run directly on the same
(LXD) controller model -- no cross-model/cross-controller offer needed.
"""

from __future__ import annotations

import jubilant


def test_s3_credentials_applied(controller: jubilant.Juju):
    controller.deploy("s3-integrator", channel="latest/stable")
    controller.wait(lambda status: "s3-integrator" in status.apps)

    controller.config(
        "s3-integrator",
        {
            "endpoint": "https://s3.example.test",
            "bucket": "juju-controller-itest",
            "region": "us-east-1",
        },
    )
    task = controller.run(
        "s3-integrator/0",
        "sync-s3-credentials",
        {"access-key": "itest-access-key", "secret-key": "itest-secret-key"},
    )
    assert task.success

    controller.integrate("controller", "s3-integrator")
    controller.wait(jubilant.all_active, timeout=600)

    # Confirm the controller charm didn't set the s3 blocked status
    # (`_stored.s3_status_error`); if credential application via the control
    # socket had failed, the controller app would be Blocked instead.
    status = controller.status()
    assert status.apps["controller"].app_status.current == "active"


def test_s3_credentials_removed(controller: jubilant.Juju):
    controller.remove_relation("controller", "s3-integrator")
    controller.wait(jubilant.all_active)

    controller.remove_application("s3-integrator")
    controller.wait(
        lambda status: "s3-integrator" not in status.apps and jubilant.all_active(status)
    )
