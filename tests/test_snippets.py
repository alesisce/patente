"""Pruebas de los favoritos de comandos."""

from __future__ import annotations

from pathlib import Path

from app.snippets import Snippets


def test_add_and_get(tmp_path: Path) -> None:
    snippets = Snippets(path=tmp_path / "snippets.json")
    assert snippets.add("saludo", "echo hola") is True
    assert snippets.names() == ["saludo"]
    assert snippets.get("saludo") == "echo hola"
    assert snippets.get("no existe") == ""


def test_add_updates_existing(tmp_path: Path) -> None:
    snippets = Snippets(path=tmp_path / "snippets.json")
    snippets.add("saludo", "echo hola")
    assert snippets.add("saludo", "echo adios") is False
    assert snippets.names() == ["saludo"]
    assert snippets.get("saludo") == "echo adios"


def test_rejects_empty_values(tmp_path: Path) -> None:
    snippets = Snippets(path=tmp_path / "snippets.json")
    assert snippets.add("", "echo hola") is False
    assert snippets.add("nombre", "   ") is False
    assert snippets.names() == []


def test_remove_and_persist(tmp_path: Path) -> None:
    path = tmp_path / "snippets.json"
    snippets = Snippets(path=path)
    snippets.add("uno", "echo 1")
    snippets.add("dos", "echo 2")
    assert snippets.remove("uno") is True
    assert snippets.remove("uno") is False

    again = Snippets(path=path)
    assert again.names() == ["dos"]


def test_tolerates_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "snippets.json"
    path.write_text("{ esto no es json", encoding="utf-8")
    snippets = Snippets(path=path)
    assert snippets.names() == []
