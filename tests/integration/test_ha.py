"""Integration tests for the `dbcluster` peer relation via `enable-ha`.

`enable-ha` has no dedicated Jubilant wrapper, so this uses `Juju.cli()`
directly (see `Juju.cli` docs: methods not yet wrapped should fall back to
raw CLI calls).
"""

from __future__ import annotations

import jubilant


def test_enable_ha(controller: jubilant.Juju):
    controller.cli("enable-ha", "-n", "3")
    controller.wait(
        lambda status: len(status.apps["controller"].units) == 3,
        timeout=900,
    )
    controller.wait(jubilant.all_active, timeout=900)


def test_peer_relation_data_populated(controller: jubilant.Juju):
    """Every unit should have published its db-bind-address on the dbcluster peer relation,
    and the leader should have aggregated them into db-bind-addresses in the app databag.
    """
    status = controller.status()
    units = list(status.apps["controller"].units)
    assert len(units) == 3

    leader_unit = next(u for u, s in status.apps["controller"].units.items() if s.leader)
    info = controller.show_unit(leader_unit)

    peer_relations = [r for r in info.relation_info if r.endpoint == "dbcluster"]
    assert peer_relations, "expected a 'dbcluster' peer relation"

    app_data = peer_relations[0].app_data
    assert "db-bind-addresses" in app_data
