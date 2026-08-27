"""Integration tests for the `website` (http) endpoint."""

from __future__ import annotations

import jubilant


def test_website_relation_sets_unit_data(controller: jubilant.Juju):
    controller.deploy("haproxy", channel="latest/stable")
    controller.integrate("controller", "haproxy")
    controller.wait(jubilant.all_active)

    # The controller charm sets hostname/private-address/port as *unit* data
    # on the website relation (see `_on_website_relation_joined`).
    info = controller.show_unit("controller/0")
    website_relations = [r for r in info.relation_info if r.endpoint == "website"]
    assert website_relations, "expected a 'website' relation on controller/0"

    local_data = website_relations[0].local_unit
    assert local_data is not None
    assert "hostname" in local_data.data
    assert "private-address" in local_data.data
    assert "port" in local_data.data


def test_remove_website_relation(controller: jubilant.Juju):
    controller.remove_application("haproxy")
    controller.wait(
        lambda status: "haproxy" not in status.apps and jubilant.all_active(status)
    )
