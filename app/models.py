"""Modelos de datos de Patente."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Server:
    """Un servidor del inventario."""

    host: str
    port: int = 22
    username: str = ""
    group: str = ""
    notes: str = ""
    enabled: bool = True
    id: str = field(default_factory=_new_id)

    @property
    def label(self) -> str:
        return f"{self.host}:{self.port}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Server":
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class ScanResult:
    """Resultado del sondeo de un host:puerto."""

    host: str
    port: int
    ok: bool = False
    is_ssh: bool = False
    latency_ms: float | None = None
    banner: str = ""
    error: str = ""

    @property
    def key(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def product(self) -> str:
        if not self.is_ssh:
            return ""
        return parse_ssh_banner(self.banner)

    @property
    def state(self) -> str:
        if not self.ok:
            return "Sin conexión"
        return "SSH" if self.is_ssh else "Puerto abierto"

    @property
    def detail(self) -> str:
        if not self.ok:
            return self.error or "Error"
        return self.product or "Sin banner SSH"


@dataclass
class ExecResult:
    """Resultado de ejecutar un comando en un servidor."""

    server_id: str
    host: str
    port: int
    command: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.exit_code == 0


def parse_ssh_banner(banner: str) -> str:
    """Extrae el software del banner: 'SSH-2.0-OpenSSH_9.6p1 Ubuntu' -> 'OpenSSH_9.6p1 Ubuntu'."""
    text = banner.strip()
    if not text.startswith("SSH-"):
        return text
    parts = text.split("-", 2)
    if len(parts) == 3:
        return parts[2]
    return text
