"""Servidor SSH mínimo de pruebas (paramiko), solo para los tests.

Escucha en 127.0.0.1 en un puerto libre y acepta autenticación por contraseña.

- `exec`: responde "eco: <comando>"; si el comando contiene "fail" devuelve
  código 1 y escribe en stderr.
- `shell`: prompt "test$ ", responde "eco: <línea>"; el comando "color"
  devuelve texto en rojo y "exit" cierra la sesión.
"""

from __future__ import annotations

import socket
import threading
import time

import paramiko


class _ServerInterface(paramiko.ServerInterface):
    def __init__(self, username: str, password: str, exec_commands: list[str]) -> None:
        self.username = username
        self.password = password
        self.exec_commands = exec_commands
        self.pending: dict[int, str] = {}
        self.shells: set[int] = set()

    def check_auth_password(self, username: str, password: str) -> int:
        if username == self.username and password == self.password:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_request(self, kind: str, chanid: int) -> int:
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        text = command.decode("utf-8", "replace") if isinstance(command, (bytes, bytearray)) else str(command)
        self.exec_commands.append(text)
        self.pending[channel.get_id()] = text
        return True

    def check_channel_shell_request(self, channel: paramiko.Channel) -> bool:
        self.shells.add(channel.get_id())
        return True

    def check_channel_pty_request(
        self,
        channel: paramiko.Channel,
        term: bytes,
        width: int,
        height: int,
        pixelwidth: int,
        pixelheight: int,
        modes: bytes,
    ) -> bool:
        return True

    def check_channel_window_change_request(
        self, channel: paramiko.Channel, width: int, height: int, pixelwidth: int, pixelheight: int
    ) -> bool:
        return True


class SSHTestServer:
    """Servidor SSH en un hilo, con parada limpia para las pruebas."""

    def __init__(self, username: str = "tester", password: str = "secreto") -> None:
        self.username = username
        self.password = password
        self.host_key = paramiko.RSAKey.generate(2048)
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._transports: list[paramiko.Transport] = []
        self.exec_commands: list[str] = []
        self.shell_input: list[str] = []
        self._thread = threading.Thread(target=self._serve, name="test-ssh-server", daemon=True)
        self._thread.start()

    # --- red ---

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                self.sock.settimeout(0.4)
                client, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client: socket.socket) -> None:
        interface = _ServerInterface(self.username, self.password, self.exec_commands)
        try:
            transport = paramiko.Transport(client)
            transport.add_server_key(self.host_key)
            transport.start_server(server=interface)
            self._transports.append(transport)
            while not self._stop.is_set() and transport.is_active():
                channel = transport.accept(0.4)
                if channel is None:
                    continue
                channel_id = channel.get_id()
                # accept() puede devolver el canal antes de que llegue la
                # petición (exec o shell); esperamos un momento a saber cuál es.
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    if channel_id in interface.shells or channel_id in interface.pending or not channel.active:
                        break
                    time.sleep(0.005)
                if channel_id in interface.shells:
                    self._serve_shell(channel)
                else:
                    self._serve_exec(channel, interface)
        except Exception:
            try:
                client.close()
            except OSError:
                pass

    def _serve_exec(self, channel: paramiko.Channel, interface: _ServerInterface) -> None:
        try:
            # Espera breve a que llegue la petición exec (accept() puede
            # devolver el canal antes de que se procese la petición).
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if channel.get_id() in interface.pending or not channel.active:
                    break
                time.sleep(0.005)
            text = interface.pending.pop(channel.get_id(), "")
            channel.sendall(f"eco: {text}\n".encode("utf-8"))
            if "fail" in text:
                channel.send_stderr(b"fallo simulado\n")
                channel.send_exit_status(1)
            else:
                channel.send_exit_status(0)
        except Exception:
            pass
        finally:
            try:
                channel.close()
            except Exception:
                pass

    def _serve_shell(self, channel: paramiko.Channel) -> None:
        try:
            channel.sendall(b"test$ ")
            buffer = b""
            channel.settimeout(0.2)
            while not self._stop.is_set():
                try:
                    data = channel.recv(4096)
                except socket.timeout:
                    continue
                except Exception:
                    break
                if not data:
                    break
                self.shell_input.append(data.decode("utf-8", "replace"))
                buffer += data
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    text = raw.decode("utf-8", "replace").strip("\r")
                    if text.strip() == "color":
                        channel.sendall(b"\x1b[31mrojo\x1b[0m\n")
                    else:
                        channel.sendall(f"eco: {text}\n".encode("utf-8"))
                    if text.strip() == "exit":
                        channel.close()
                        return
                    channel.sendall(b"test$ ")
        except Exception:
            pass
        finally:
            try:
                channel.close()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass
        for transport in list(self._transports):
            try:
                transport.close()
            except Exception:
                pass
        self._thread.join(timeout=2.0)
