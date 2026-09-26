"""Sesión SSH sobre paramiko: conexión, estado y ejecución de comandos."""

from __future__ import annotations

import socket
import threading
import time

import paramiko

from ..events import EventBus, SessionChanged, ShellClosed, ShellOpened, ShellOutput
from ..log import AppLog
from ..models import ExecResult, Server

# Estados de una sesión
DISCONNECTED = "disconnected"
CONNECTING = "connecting"
RECONNECTING = "reconnecting"
CONNECTED = "connected"
ERROR = "error"

MAX_BACKOFF_EXPONENT = 6


def friendly_ssh_error(exc: BaseException) -> str:
    """Traduce excepciones de paramiko a mensajes en español."""
    if isinstance(exc, paramiko.AuthenticationException):
        return "Usuario o contraseña incorrectos"
    if isinstance(exc, paramiko.BadHostKeyException):
        return "La clave del servidor no coincide con known_hosts"
    if isinstance(exc, paramiko.ssh_exception.NoValidConnectionsError):
        return "Conexión rechazada"
    if isinstance(exc, socket.gaierror):
        return "No se pudo resolver el nombre"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "Tiempo de espera agotado"
    text = str(exc)
    if "Error reading SSH protocol banner" in text:
        return "El puerto no parece un servidor SSH"
    return text or exc.__class__.__name__


class SSHSession:
    """Una conexión SSH con estado, credencial en memoria y reconexión.

    La contraseña vive únicamente en memoria; si `remember` es False se
    descarta tras el primer intento y no habrá reconexión automática.
    """

    def __init__(self, server: Server, bus: EventBus, log: AppLog, settings: dict) -> None:
        self.server = server
        self.bus = bus
        self.log = log
        self._ssh_settings = dict(settings.get("ssh", {}))

        self.state = DISCONNECTED
        self.detail = ""
        self.remote_version = ""
        self.fingerprint = ""
        self.connected_at: float | None = None

        self._lock = threading.RLock()
        self._client: paramiko.SSHClient | None = None
        self._username = server.username
        self._password: str | None = None
        self._attempt_password: str | None = None
        self._remember = True
        self._want_connected = False
        self._connecting = False
        self._retry_count = 0
        self._next_retry_at = 0.0

        # Shell interactiva
        self._shell: paramiko.Channel | None = None
        self._shell_reader: threading.Thread | None = None
        self._shell_stop = threading.Event()
        self._shell_close_reason = ""
        self.shell_size = (0, 0)

    # --- estado (thread-safe) ---

    @property
    def connecting(self) -> bool:
        with self._lock:
            return self._connecting

    @connecting.setter
    def connecting(self, value: bool) -> None:
        with self._lock:
            self._connecting = value

    @property
    def want_connected(self) -> bool:
        with self._lock:
            return self._want_connected

    @property
    def can_retry(self) -> bool:
        with self._lock:
            auto = bool(self._ssh_settings.get("auto_reconnect", True))
            return self._want_connected and auto and self._password is not None

    @property
    def next_retry_at(self) -> float:
        with self._lock:
            return self._next_retry_at

    def is_alive(self) -> bool:
        with self._lock:
            client = self._client
        if client is None:
            return False
        transport = client.get_transport()
        return bool(transport is not None and transport.is_active())

    # --- credenciales ---

    @property
    def username(self) -> str:
        with self._lock:
            return self._username

    @property
    def has_credential(self) -> bool:
        with self._lock:
            return self._password is not None

    def request_connect(self, username: str, password: str, remember: bool = True) -> None:
        with self._lock:
            self._username = username.strip() or self.server.username
            self._attempt_password = password
            self._password = password if remember else None
            self._remember = remember
            self._want_connected = True
            self._retry_count = 0
            self._next_retry_at = 0.0
        self._set_state(CONNECTING)

    def cancel_want(self) -> None:
        """Olvida la credencial y desactiva la reconexión automática."""
        with self._lock:
            self._want_connected = False
            self._attempt_password = None
            self._password = None
            self._retry_count = 0
            self._next_retry_at = 0.0

    # --- ciclo de conexión ---

    def begin_attempt(self, reconnecting: bool) -> None:
        self._set_state(RECONNECTING if reconnecting else CONNECTING)

    def connect_once(self) -> bool:
        """Un intento de conexión. Devuelve True si quedó conectada."""
        with self._lock:
            username = self._username or self.server.username
            password = self._password if self._password is not None else self._attempt_password
            remember = self._remember
        if not password:
            self._set_state(ERROR, "Falta la contraseña")
            self.cancel_want()
            return False

        timeout = float(self._ssh_settings.get("connect_timeout", 10.0))
        auth_timeout = float(self._ssh_settings.get("auth_timeout", 15.0))
        keepalive = int(self._ssh_settings.get("keepalive", 30))
        policy = str(self._ssh_settings.get("host_key_policy", "auto")).lower()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(
            paramiko.AutoAddPolicy() if policy == "auto" else paramiko.RejectPolicy()
        )
        try:
            client.connect(
                hostname=self.server.host,
                port=self.server.port,
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=timeout,
                auth_timeout=auth_timeout,
                allow_agent=False,
                look_for_keys=False,
            )
        except (paramiko.AuthenticationException, paramiko.BadHostKeyException) as exc:
            # Error permanente: no tiene sentido reintentar con la misma credencial.
            self._close_client_silently(client)
            with self._lock:
                self._want_connected = False
                self._attempt_password = None
                self._password = None
            message = friendly_ssh_error(exc)
            self._set_state(ERROR, message)
            self.log.warn(f"SSH {self.server.label}: {message}")
            return False
        except (paramiko.SSHException, OSError, EOFError, TimeoutError) as exc:
            self._close_client_silently(client)
            with self._lock:
                if not remember:
                    self._want_connected = False
                    self._attempt_password = None
                self._retry_count += 1
                base = float(self._ssh_settings.get("reconnect_base_delay", 3.0))
                top = float(self._ssh_settings.get("reconnect_max_delay", 60.0))
                exponent = min(self._retry_count - 1, MAX_BACKOFF_EXPONENT)
                self._next_retry_at = time.monotonic() + min(top, base * (2**exponent))
            message = friendly_ssh_error(exc)
            self._set_state(ERROR, message)
            self.log.warn(f"SSH {self.server.label}: {message}")
            return False

        transport = client.get_transport()
        if transport is not None:
            transport.set_keepalive(keepalive)
        with self._lock:
            self._client = client
            self._attempt_password = None
            self._retry_count = 0
            self._next_retry_at = 0.0
        self.remote_version = (transport.remote_version or "") if transport else ""
        self.fingerprint = self._fingerprint(transport)
        self.connected_at = time.time()
        self._set_state(CONNECTED, self.remote_version)
        self.log.ok(
            f"SSH conectado a {self.server.label} "
            f"({self.remote_version or 'versión desconocida'}; {self.fingerprint or 'sin huella'})"
        )
        return True

    def disconnect(self) -> None:
        self.close_shell("Desconectado")
        self.cancel_want()
        self._close_client()
        self.connected_at = None
        self.remote_version = ""
        self._set_state(DISCONNECTED)

    def mark_lost(self, reason: str = "Conexión perdida") -> None:
        """La conexión se cayó; el monitor decidirá si reconectar."""
        self.close_shell(reason)
        self._close_client()
        self.connected_at = None
        if self.can_retry:
            with self._lock:
                self._next_retry_at = 0.0
            self._set_state(RECONNECTING, reason)
        else:
            self._set_state(DISCONNECTED, reason)
        self.log.warn(f"SSH {self.server.label}: {reason}")

    # --- ejecución remota ---

    def run(self, command: str, timeout: float = 30.0) -> ExecResult:
        """Ejecuta un comando y devuelve su salida. Usado por el envío masivo."""
        started = time.perf_counter()
        with self._lock:
            client = self._client

        def _result(**kwargs) -> ExecResult:
            return ExecResult(
                server_id=self.server.id,
                host=self.server.host,
                port=self.server.port,
                command=command,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                **kwargs,
            )

        if client is None:
            return _result(error="Sin conexión SSH")
        try:
            _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            errors = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            return _result(exit_code=exit_code, stdout=output, stderr=errors)
        except (paramiko.SSHException, OSError, EOFError) as exc:
            message = friendly_ssh_error(exc)
            self.mark_lost(message)
            return _result(error=message)

    # --- shell interactiva ---

    @property
    def shell_active(self) -> bool:
        with self._lock:
            channel = self._shell
        return channel is not None and not channel.closed

    def open_shell(self, cols: int = 120, rows: int = 32) -> bool:
        """Abre una shell interactiva (pty) y arranca el hilo lector."""
        with self._lock:
            if self._shell is not None and not self._shell.closed:
                return True
            client = self._client
        if client is None or not self.is_alive():
            self.bus.publish(ShellClosed(server_id=self.server.id, reason="Sin conexión SSH"))
            return False
        try:
            channel = client.invoke_shell(
                term="xterm-256color", width=max(20, int(cols)), height=max(5, int(rows))
            )
        except (paramiko.SSHException, OSError, EOFError) as exc:
            message = friendly_ssh_error(exc)
            self.log.warn(f"Shell {self.server.label}: {message}")
            self.bus.publish(ShellClosed(server_id=self.server.id, reason=message))
            return False
        channel.settimeout(0.2)
        with self._lock:
            self._shell = channel
            self._shell_close_reason = ""
            self.shell_size = (max(20, int(cols)), max(5, int(rows)))
        self._shell_stop.clear()
        self.bus.publish(ShellOpened(server_id=self.server.id))
        self._shell_reader = threading.Thread(
            target=self._read_shell,
            args=(channel,),
            name=f"patente-shell-{self.server.host}",
            daemon=True,
        )
        self._shell_reader.start()
        self.log.ok(f"Shell abierta en {self.server.label} ({self.shell_size[0]}×{self.shell_size[1]})")
        return True

    def send_shell(self, text: str) -> bool:
        with self._lock:
            channel = self._shell
        if channel is None:
            return False
        try:
            channel.send(text)
            return True
        except (paramiko.SSHException, OSError, EOFError) as exc:
            self.mark_lost(friendly_ssh_error(exc))
            return False

    def resize_shell(self, cols: int, rows: int) -> bool:
        with self._lock:
            channel = self._shell
        if channel is None:
            return False
        cols, rows = max(20, int(cols)), max(5, int(rows))
        if (cols, rows) == self.shell_size:
            return True
        try:
            channel.resize_pty(width=cols, height=rows)
            self.shell_size = (cols, rows)
            return True
        except (paramiko.SSHException, OSError):
            return False

    def close_shell(self, reason: str = "Cerrada por el usuario") -> None:
        with self._lock:
            channel = self._shell
            self._shell_close_reason = reason
        self._shell_stop.set()
        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass

    def _read_shell(self, channel: paramiko.Channel) -> None:
        reason = ""
        try:
            while not self._shell_stop.is_set():
                try:
                    data = channel.recv(65536)
                except (TimeoutError, socket.timeout):
                    if channel.closed:
                        break
                    continue
                except (paramiko.SSHException, OSError, EOFError) as exc:
                    reason = friendly_ssh_error(exc)
                    break
                if not data:
                    break
                self.bus.publish(
                    ShellOutput(server_id=self.server.id, data=data.decode("utf-8", errors="replace"))
                )
        finally:
            with self._lock:
                owner = self._shell is channel
                if owner:
                    self._shell = None
                stored_reason = self._shell_close_reason
            self._shell_stop.set()
            if owner:
                message = stored_reason or reason or "La shell se cerró"
                self.bus.publish(ShellClosed(server_id=self.server.id, reason=message))
                self.log.info(f"Shell cerrada en {self.server.label}: {message}")

    # --- interno ---

    def _set_state(self, state: str, detail: str = "") -> None:
        with self._lock:
            self.state = state
            self.detail = detail
        self.bus.publish(SessionChanged(server_id=self.server.id, state=state, detail=detail))

    def _close_client(self) -> None:
        with self._lock:
            client, self._client = self._client, None
        self._close_client_silently(client)

    @staticmethod
    def _close_client_silently(client: paramiko.SSHClient | None) -> None:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    @staticmethod
    def _fingerprint(transport: paramiko.Transport | None) -> str:
        if transport is None:
            return ""
        try:
            key = transport.get_remote_server_key()
            return f"{key.get_name()} {key.get_base64()[:24]}…"
        except Exception:
            return ""
