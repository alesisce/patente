"""Gestor de conexiones SSH: pool de sesiones, monitor y reconexión."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from ..events import EventBus
from ..inventory import Inventory
from ..log import AppLog
from ..models import Server
from .session import CONNECTED, SSHSession


class ConnectionManager:
    """Crea y vigila una SSHSession por servidor.

    Los intentos de conexión corren en un pool de hilos; un monitor revisa
    cada pocos segundos las sesiones caídas y reintenta con backoff
    exponencial mientras haya credencial en memoria.
    """

    def __init__(
        self,
        inventory: Inventory | None,
        bus: EventBus,
        log: AppLog,
        settings: dict,
    ) -> None:
        self.inventory = inventory
        self.bus = bus
        self.log = log
        self.settings = settings
        self._ssh_settings = dict(settings.get("ssh", {}))
        self._sessions: dict[str, SSHSession] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="patente-ssh")

    # --- ciclo de vida ---

    def start(self) -> None:
        if self._monitor is None:
            self._monitor = threading.Thread(
                target=self._monitor_loop, name="patente-ssh-monitor", daemon=True
            )
            self._monitor.start()

    def stop(self) -> None:
        self._stop.set()
        if self._monitor is not None:
            self._monitor.join(timeout=2.0)
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.disconnect()
        self._executor.shutdown(wait=False, cancel_futures=True)

    # --- consultas ---

    @property
    def sessions(self) -> dict[str, SSHSession]:
        return self._sessions

    def find(self, server_id: str) -> SSHSession | None:
        return self._sessions.get(server_id)

    def session_for(self, server: Server) -> SSHSession:
        with self._lock:
            session = self._sessions.get(server.id)
            if session is None:
                session = SSHSession(server, self.bus, self.log, self.settings)
                self._sessions[server.id] = session
            return session

    def connected_count(self) -> int:
        return sum(1 for session in self._sessions.values() if session.state == CONNECTED)

    def prune(self, valid_ids: set[str]) -> None:
        """Cierra y olvida sesiones de servidores que ya no están en el inventario."""
        with self._lock:
            stale = [server_id for server_id in self._sessions if server_id not in valid_ids]
        for server_id in stale:
            session = self._sessions.pop(server_id, None)
            if session is not None:
                session.disconnect()

    # --- acciones ---

    def connect(self, server: Server, username: str = "", password: str = "", remember: bool = True) -> None:
        session = self.session_for(server)
        if session.state == CONNECTED:
            self.log.info(f"SSH {server.label}: ya está conectado")
            return
        if session.connecting:
            self.log.info(f"SSH {server.label}: ya hay una conexión en curso")
            return
        session.request_connect(username, password, remember)
        self._kick(session)

    def connect_many(self, entries: Iterable[tuple[Server, str, str, bool]]) -> None:
        for server, username, password, remember in entries:
            self.connect(server, username, password, remember)

    def disconnect(self, server_id: str) -> None:
        session = self.find(server_id)
        if session is not None:
            label = session.server.label
            session.disconnect()
            self.log.info(f"SSH {label}: desconectado")

    def disconnect_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.disconnect()

    # --- interno ---

    def _kick(self, session: SSHSession, reconnecting: bool = False) -> None:
        if session.connecting:
            return
        session.connecting = True
        if reconnecting:
            session.begin_attempt(reconnecting=True)
        self._executor.submit(self._run_attempt, session)

    def _run_attempt(self, session: SSHSession) -> None:
        try:
            session.connect_once()
        except Exception as exc:  # protección: el pool nunca debe romperse
            self.log.error(f"SSH {session.server.label}: error inesperado al conectar ({exc})")
        finally:
            session.connecting = False

    def _monitor_loop(self) -> None:
        interval = max(0.05, float(self._ssh_settings.get("monitor_interval", 2.0)))
        while not self._stop.wait(interval):
            now = time.monotonic()
            with self._lock:
                sessions = list(self._sessions.values())
            for session in sessions:
                try:
                    self._monitor_session(session, now)
                except Exception as exc:
                    self.log.error(f"Monitor SSH: error con {session.server.label} ({exc})")

    def _monitor_session(self, session: SSHSession, now: float) -> None:
        if session.connecting or not session.want_connected:
            return
        if session.is_alive():
            return
        if session.state == CONNECTED:
            session.mark_lost()
        if not session.can_retry or now < session.next_retry_at:
            return
        self._kick(session, reconnecting=True)
