"""Inventario de servidores: persistencia, altas, bajas y exportación."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from . import config
from .events import EventBus, ServersChanged
from .log import AppLog
from .models import Server


class Inventory:
    """Lista de servidores con guardado automático en disco."""

    def __init__(self, path: Path | None = None, bus: EventBus | None = None, log: AppLog | None = None) -> None:
        self.path = Path(path) if path else config.servers_path()
        self.bus = bus
        self.log = log
        self.servers: list[Server] = []
        self.load()

    # --- persistencia ---

    def load(self) -> None:
        self.servers = []
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._warn(f"No se pudo leer el inventario ({self.path}): {exc}")
            return
        raw = data.get("servers", []) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                self.servers.append(Server.from_dict(item))
            except TypeError:
                continue

    def save(self) -> None:
        payload = {"version": 1, "servers": [server.to_dict() for server in self.servers]}
        try:
            config.atomic_write_json(self.path, payload)
        except OSError as exc:
            self._warn(f"No se pudo guardar el inventario: {exc}")

    # --- consultas ---

    def find(self, host: str, port: int) -> Server | None:
        host = host.strip().lower()
        for server in self.servers:
            if server.host == host and server.port == port:
                return server
        return None

    @property
    def enabled_servers(self) -> list[Server]:
        return [server for server in self.servers if server.enabled]

    def counts(self) -> tuple[int, int]:
        active = sum(1 for server in self.servers if server.enabled)
        return len(self.servers), active

    # --- mutaciones ---

    def add(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        group: str = "",
        notes: str = "",
        enabled: bool = True,
    ) -> Server | None:
        """Añade un servidor. Devuelve None si ya existía."""
        host = host.strip().lower()
        port = int(port)
        if not host:
            raise ValueError("El host no puede estar vacío")
        if self.find(host, port):
            return None
        server = Server(
            host=host,
            port=port,
            username=username.strip(),
            group=group.strip(),
            notes=notes.strip(),
            enabled=enabled,
        )
        self.servers.append(server)
        self._changed("add")
        return server

    def add_many(self, items: Iterable[tuple[str, int]]) -> tuple[int, int]:
        """Añade varios (host, puerto). Devuelve (añadidos, omitidos)."""
        added = skipped = 0
        for host, port in items:
            host = str(host).strip().lower()
            try:
                port = int(port)
            except (TypeError, ValueError):
                skipped += 1
                continue
            if not host or self.find(host, port):
                skipped += 1
                continue
            self.servers.append(Server(host=host, port=port))
            added += 1
        if added:
            self._changed("add")
        return added, skipped

    def remove_ids(self, ids: Iterable[str]) -> int:
        ids = set(ids)
        before = len(self.servers)
        self.servers = [server for server in self.servers if server.id not in ids]
        removed = before - len(self.servers)
        if removed:
            self._changed("remove")
        return removed

    def set_enabled(self, ids: Iterable[str], enabled: bool) -> int:
        ids = set(ids)
        changed = 0
        for server in self.servers:
            if server.id in ids and server.enabled != enabled:
                server.enabled = enabled
                changed += 1
        if changed:
            self._changed("enable")
        return changed

    # --- exportación e importación ---

    def export_file(self, path: str | Path) -> int:
        """Exporta el inventario a .json o .csv. Devuelve el número de servidores."""
        path = Path(path)
        if path.suffix.lower() == ".json":
            config.atomic_write_json(path, {"version": 1, "servers": [s.to_dict() for s in self.servers]})
        else:
            if path.suffix.lower() != ".csv":
                path = path.with_suffix(".csv")
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["host", "port", "username", "group", "notes", "enabled"],
                    lineterminator="\n",
                )
                writer.writeheader()
                for server in self.servers:
                    row = server.to_dict()
                    writer.writerow({key: row[key] for key in writer.fieldnames})
        return len(self.servers)

    def import_file(self, path: str | Path) -> tuple[int, int]:
        """Importa desde .json o .csv. Devuelve (añadidos, omitidos)."""
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("servers", []) if isinstance(data, dict) else data
            entries = [item for item in raw if isinstance(item, dict)]
        elif suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                entries = list(csv.DictReader(handle))
        else:
            raise ValueError(f"Formato no soportado: {path.name}")

        added = skipped = 0
        for entry in entries:
            host = str(entry.get("host", "")).strip().lower()
            try:
                port = int(str(entry.get("port", "22")).strip() or 22)
            except ValueError:
                skipped += 1
                continue
            if not host or self.find(host, port):
                skipped += 1
                continue
            enabled_raw = str(entry.get("enabled", "true")).strip().lower()
            self.servers.append(
                Server(
                    host=host,
                    port=port,
                    username=str(entry.get("username", "")).strip(),
                    group=str(entry.get("group", "")).strip(),
                    notes=str(entry.get("notes", "")).strip(),
                    enabled=enabled_raw not in ("false", "0", "no"),
                )
            )
            added += 1
        if added:
            self._changed("import")
        return added, skipped

    # --- interno ---

    def _changed(self, reason: str) -> None:
        self.save()
        if self.bus is not None:
            self.bus.publish(ServersChanged(reason=reason))

    def _warn(self, message: str) -> None:
        if self.log is not None:
            self.log.warn(message)
