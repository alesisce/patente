"""Favoritos de comandos (nombres con un comando asociado)."""

from __future__ import annotations

import json
from pathlib import Path

from . import config


class Snippets:
    """Lista de favoritos guardada en el directorio de datos."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else config.data_dir() / "snippets.json"
        self.items: list[dict[str, str]] = []
        self.load()

    def load(self) -> None:
        self.items = []
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        raw = data.get("favoritos", []) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return
        for item in raw:
            if isinstance(item, dict) and item.get("nombre") and item.get("comando"):
                self.items.append({"nombre": str(item["nombre"]), "comando": str(item["comando"])})

    def save(self) -> None:
        try:
            config.atomic_write_json(self.path, {"version": 1, "favoritos": self.items})
        except OSError:
            pass

    def names(self) -> list[str]:
        return [item["nombre"] for item in self.items]

    def get(self, name: str) -> str:
        for item in self.items:
            if item["nombre"] == name:
                return item["comando"]
        return ""

    def add(self, name: str, command: str) -> bool:
        """Añade o actualiza un favorito. Devuelve True si lo añadió."""
        name = name.strip()
        command = command.strip()
        if not name or not command:
            return False
        for item in self.items:
            if item["nombre"] == name:
                item["comando"] = command
                self.save()
                return False
        self.items.append({"nombre": name, "comando": command})
        self.save()
        return True

    def remove(self, name: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item["nombre"] != name]
        if len(self.items) != before:
            self.save()
            return True
        return False
