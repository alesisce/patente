"""Pruebas de integración de SSHSession y ConnectionManager con un servidor local."""

from __future__ import annotations

import time

import pytest

from app.events import EventBus
from app.log import AppLog
from app.models import Server
from app.ssh.manager import ConnectionManager
from app.ssh.session import CONNECTED, DISCONNECTED, ERROR, SSHSession
from support_ssh_server import SSHTestServer


def _settings(**overrides) -> dict:
    settings = {
        "ssh": {
            "connect_timeout": 3.0,
            "auth_timeout": 5.0,
            "keepalive": 1,
            "auto_reconnect": True,
            "reconnect_base_delay": 0.05,
            "reconnect_max_delay": 0.2,
            "monitor_interval": 0.05,
            "host_key_policy": "auto",
        }
    }
    settings["ssh"].update(overrides)
    return settings


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.03)
    return False


@pytest.fixture()
def ssh_server():
    server = SSHTestServer(username="tester", password="secreto")
    yield server
    server.stop()


def _session(ssh_server: SSHTestServer, **overrides) -> SSHSession:
    bus = EventBus()
    log = AppLog(bus)
    server = Server(host="127.0.0.1", port=ssh_server.port, username="tester")
    return SSHSession(server, bus, log, _settings(**overrides))


def test_connect_run_and_disconnect(ssh_server: SSHTestServer) -> None:
    session = _session(ssh_server)
    session.request_connect("tester", "secreto", remember=True)
    assert session.connect_once() is True
    assert session.state == CONNECTED
    assert session.is_alive()

    result = session.run("echo hola")
    assert result.exit_code == 0
    assert "hola" in result.stdout
    assert result.error == ""

    failed = session.run("comando fail")
    assert failed.exit_code == 1
    assert "fallo simulado" in failed.stderr

    session.disconnect()
    assert session.state == DISCONNECTED
    assert not session.is_alive()


def test_wrong_password_is_permanent(ssh_server: SSHTestServer) -> None:
    session = _session(ssh_server)
    session.request_connect("tester", "incorrecta", remember=True)
    assert session.connect_once() is False
    assert session.state == ERROR
    assert "incorrect" in session.detail.lower()
    assert session.want_connected is False
    assert session.can_retry is False


def test_no_remember_disables_reconnect(ssh_server: SSHTestServer) -> None:
    session = _session(ssh_server)
    session.request_connect("tester", "secreto", remember=False)
    assert session.connect_once() is True
    assert session.state == CONNECTED
    assert session.has_credential is False
    assert session.can_retry is False


def test_manager_reconnects_after_loss(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    log = AppLog(bus)
    manager = ConnectionManager(inventory=None, bus=bus, log=log, settings=_settings())
    manager.start()
    try:
        server = Server(host="127.0.0.1", port=ssh_server.port, username="tester")
        manager.connect(server, "tester", "secreto", remember=True)
        assert _wait_for(lambda: (manager.find(server.id) or None) is not None)
        session = manager.find(server.id)
        assert session is not None
        assert _wait_for(lambda: session.state == CONNECTED)

        session.mark_lost("prueba de caída")
        # El monitor debe reconectar solo, sin intervención del usuario.
        assert _wait_for(lambda: session.state == CONNECTED)
        assert manager.connected_count() == 1
    finally:
        manager.stop()


def test_manager_disconnect_and_prune(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    log = AppLog(bus)
    manager = ConnectionManager(inventory=None, bus=bus, log=log, settings=_settings())
    manager.start()
    try:
        server = Server(host="127.0.0.1", port=ssh_server.port, username="tester")
        manager.connect(server, "tester", "secreto", remember=True)
        session = manager.session_for(server)
        assert _wait_for(lambda: session.state == CONNECTED)

        manager.disconnect(server.id)
        assert session.state == DISCONNECTED

        manager.connect(server, "tester", "secreto", remember=True)
        assert _wait_for(lambda: session.state == CONNECTED)
        manager.prune(set())  # ya no está en el inventario
        assert manager.find(server.id) is None
        assert session.state == DISCONNECTED
    finally:
        manager.stop()
