"""Pruebas de integración de las shells interactivas."""

from __future__ import annotations

import time

import pytest

from app.events import EventBus, ShellClosed, ShellOutput
from app.log import AppLog
from app.models import Server
from app.ssh.session import SSHSession
from support_ssh_server import SSHTestServer


def _settings() -> dict:
    return {
        "ssh": {
            "connect_timeout": 3.0,
            "auth_timeout": 5.0,
            "keepalive": 1,
            "auto_reconnect": False,
            "reconnect_base_delay": 0.05,
            "reconnect_max_delay": 0.2,
            "monitor_interval": 0.05,
            "host_key_policy": "auto",
        }
    }


@pytest.fixture()
def ssh_server():
    server = SSHTestServer(username="tester", password="secreto")
    yield server
    server.stop()


def _connected(ssh_server: SSHTestServer) -> SSHSession:
    bus = EventBus()
    log = AppLog(bus)
    server = Server(host="127.0.0.1", port=ssh_server.port, username="tester")
    session = SSHSession(server, bus, log, _settings())
    session.request_connect("tester", "secreto", remember=True)
    assert session.connect_once() is True
    return session


def _wait_events(bus: EventBus, predicate, timeout: float = 5.0) -> list:
    collected: list = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in bus.drain():
            collected.append(event)
            if predicate(collected):
                return collected
        time.sleep(0.02)
    return collected


def test_open_shell_send_and_receive(ssh_server: SSHTestServer) -> None:
    session = _connected(ssh_server)
    assert session.open_shell(cols=90, rows=25) is True
    assert session.shell_active
    assert session.shell_size == (90, 25)

    session.send_shell("hola\n")
    events = _wait_events(
        session.bus,
        lambda collected: any(
            isinstance(event, ShellOutput) and "eco: hola" in event.data for event in collected
        ),
    )
    assert any(isinstance(event, ShellOutput) and "eco: hola" in event.data for event in events)
    assert session.shell_active


def test_shell_output_preserves_ansi(ssh_server: SSHTestServer) -> None:
    session = _connected(ssh_server)
    session.open_shell()
    session.send_shell("color\n")
    events = _wait_events(
        session.bus,
        lambda collected: any(
            isinstance(event, ShellOutput) and "\x1b[31m" in event.data for event in collected
        ),
    )
    assert any(isinstance(event, ShellOutput) and "\x1b[31m" in event.data for event in events)


def test_resize_shell(ssh_server: SSHTestServer) -> None:
    session = _connected(ssh_server)
    session.open_shell(cols=80, rows=24)
    assert session.resize_shell(120, 40) is True
    assert session.shell_size == (120, 40)


def test_close_shell_publishes_event(ssh_server: SSHTestServer) -> None:
    session = _connected(ssh_server)
    session.open_shell()
    session.close_shell("prueba")
    events = _wait_events(session.bus, lambda collected: any(isinstance(e, ShellClosed) for e in collected))
    assert any(isinstance(event, ShellClosed) for event in events)
    assert not session.shell_active
    assert session.send_shell("x\n") is False


def test_disconnect_closes_shell(ssh_server: SSHTestServer) -> None:
    session = _connected(ssh_server)
    session.open_shell()
    assert session.shell_active
    session.disconnect()
    assert not session.shell_active
    events = _wait_events(session.bus, lambda collected: any(isinstance(e, ShellClosed) for e in collected))
    assert any(isinstance(event, ShellClosed) for event in events)


def test_open_shell_without_connection(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    server = Server(host="127.0.0.1", port=ssh_server.port, username="tester")
    session = SSHSession(server, bus, AppLog(bus), _settings())
    assert session.open_shell() is False
    assert not session.shell_active
