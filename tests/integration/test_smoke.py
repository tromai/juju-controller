from __future__ import annotations

import jubilant


def test_controller_charm_is_active():
    controller = jubilant.Juju(model="controller")
    controller.wait(lambda status: jubilant.all_active(status, 'controller'), timeout=10,)