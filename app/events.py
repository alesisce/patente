"""Eventos de la aplicación y bus de comunicación entre hilos y la interfaz."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Union

from .models import ExecResult, ScanResult


@dataclass
class LogEvent:
    level: str
    message: str
    ts: float


@dataclass
class StatusEvent:
    message: str


@dataclass
class ServersChanged:
    reason: str = ""


@dataclass
class SessionChanged:
    server_id: str
    state: str
    detail: str = ""


@dataclass
class ScanStarted:
    total: int


@dataclass
class ScanProgress:
    done: int
    total: int


@dataclass
class ScanHostResult:
    result: ScanResult


@dataclass
class ScanFinished:
    done: int
    total: int
    stopped: bool


@dataclass
class BroadcastStarted:
    total: int
    servers: int
    commands: int


@dataclass
class BroadcastResult:
    result: ExecResult
    command_index: int
    command_count: int


@dataclass
class BroadcastProgress:
    done: int
    total: int
    skipped: int = 0
    failed: int = 0


@dataclass
class BroadcastServerSkipped:
    label: str
    remaining: int
    reason: str = ""


@dataclass
class BroadcastFinished:
    done: int
    total: int
    skipped: int
    failed: int
    stopped: bool


@dataclass
class ShellOpened:
    server_id: str


@dataclass
class ShellOutput:
    server_id: str
    data: str


@dataclass
class ShellClosed:
    server_id: str
    reason: str = ""


Event = Union[
    LogEvent,
    StatusEvent,
    ServersChanged,
    SessionChanged,
    ScanStarted,
    ScanProgress,
    ScanHostResult,
    ScanFinished,
    BroadcastStarted,
    BroadcastResult,
    BroadcastProgress,
    BroadcastServerSkipped,
    BroadcastFinished,
    ShellOpened,
    ShellOutput,
    ShellClosed,
]


class EventBus:
    """Cola de eventos segura entre hilos. La interfaz la vacía en cada fotograma."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[Event]" = queue.Queue()

    def publish(self, event: Event) -> None:
        self._queue.put(event)

    def drain(self) -> list[Event]:
        events: list[Event] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                return events
