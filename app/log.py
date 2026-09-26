"""Registro de la aplicación: a archivo y al panel de la interfaz."""

from __future__ import annotations

import threading
import time
from datetime import datetime

from . import config
from .events import EventBus, LogEvent


class AppLog:
    """Escribe en el archivo de registro y publica LogEvent para la interfaz."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._lock = threading.Lock()
        self.path = config.log_dir() / f"patente-{datetime.now():%Y-%m-%d}.log"

    def _emit(self, level: str, message: str) -> None:
        now = time.time()
        self.bus.publish(LogEvent(level=level, message=f"[{datetime.fromtimestamp(now):%H:%M:%S}] {message}", ts=now))
        try:
            with self._lock:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{datetime.fromtimestamp(now).isoformat(timespec='seconds')}\t{level}\t{message}\n")
        except OSError:
            pass

    def info(self, message: str) -> None:
        self._emit("info", message)

    def ok(self, message: str) -> None:
        self._emit("ok", message)

    def warn(self, message: str) -> None:
        self._emit("warn", message)

    def error(self, message: str) -> None:
        self._emit("error", message)
