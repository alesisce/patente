"""Pruebas del inventario: altas, bajas, exclusión y exportación."""

from __future__ import annotations

from pathlib import Path

from app.inventory import Inventory


def _inventory(tmp_path: Path) -> Inventory:
    return Inventory(path=tmp_path / "servers.json")


def test_add_and_dedupe(tmp_path: Path) -> None:
    inv = _inventory(tmp_path)
    assert inv.add("10.0.0.1") is not None
    assert inv.add("10.0.0.1") is None  # duplicado
    assert inv.add("10.0.0.1", 2222) is not None

    added, skipped = inv.add_many([("10.0.0.2", 22), ("10.0.0.1", 22), ("10.0.0.3", 22)])
    assert (added, skipped) == (2, 1)
    assert inv.counts() == (4, 4)


def test_remove_and_enabled(tmp_path: Path) -> None:
    inv = _inventory(tmp_path)
    inv.add_many([("10.0.0.1", 22), ("10.0.0.2", 22)])
    first = inv.servers[0]
    assert inv.set_enabled([first.id], False) == 1
    assert inv.counts() == (2, 1)
    assert inv.set_enabled([first.id], False) == 0  # sin cambios
    assert inv.remove_ids([first.id]) == 1
    assert inv.counts() == (1, 1)


def test_persistence(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    inv = Inventory(path=path)
    inv.add("10.9.9.9", 22, username="admin", group="lab", notes="nota")
    assert path.exists()

    again = Inventory(path=path)
    assert len(again.servers) == 1
    server = again.servers[0]
    assert (server.host, server.port, server.username, server.group, server.notes) == (
        "10.9.9.9",
        22,
        "admin",
        "lab",
        "nota",
    )


def test_csv_roundtrip(tmp_path: Path) -> None:
    source = _inventory(tmp_path / "a")
    source.add("10.0.0.1", 22, username="root", group="g1")
    source.add("10.0.0.2", 2222, enabled=False)
    csv_path = tmp_path / "export.csv"
    assert source.export_file(csv_path) == 2

    target = Inventory(path=tmp_path / "b" / "servers.json")
    added, skipped = target.import_file(csv_path)
    assert (added, skipped) == (2, 0)
    assert target.servers[1].enabled is False

    # Importar otra vez no debe duplicar
    assert target.import_file(csv_path) == (0, 2)


def test_json_roundtrip(tmp_path: Path) -> None:
    source = _inventory(tmp_path / "a")
    source.add("10.0.0.3", 2200, group="dmz")
    json_path = tmp_path / "export.json"
    assert source.export_file(json_path) == 1

    target = Inventory(path=tmp_path / "b" / "servers.json")
    assert target.import_file(json_path) == (1, 0)
    assert target.servers[0].group == "dmz"
