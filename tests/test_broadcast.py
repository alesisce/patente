"""Pruebas de integración del envío masivo de comandos."""

from __future__ import annotations

import time

import pytest

from app.events import (
    BroadcastFinished,
    BroadcastResult,
    BroadcastServerSkipped,
    EventBus,
)
from app.log import AppLog
from app.models import Server
from app.ssh.broadcast import BroadcastRunner
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


def _connected_session(ssh_server: SSHTestServer, bus: EventBus, log: AppLog) -> SSHSession:
    server = Server(host="127.0.0.1", port=ssh_server.port, username="tester")
    session = SSHSession(server, bus, log, _settings())
    session.request_connect("tester", "secreto", remember=True)
    assert session.connect_once() is True
    return session


def _disconnected_session(ssh_server: SSHTestServer, bus: EventBus, log: AppLog) -> SSHSession:
    server = Server(host="127.0.0.1", port=ssh_server.port, username="tester")
    return SSHSession(server, bus, log, _settings())


def _run_and_collect(runner: BroadcastRunner, bus: EventBus, sessions, commands, **kwargs) -> dict:
    runner.start(sessions, commands, **kwargs)
    results = []
    skipped = []
    finished = None
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        for event in bus.drain():
            if isinstance(event, BroadcastResult):
                results.append(event.result)
            elif isinstance(event, BroadcastServerSkipped):
                skipped.append(event)
            elif isinstance(event, BroadcastFinished):
                finished = event
        if finished is not None and not runner.running:
            break
        time.sleep(0.02)
    assert finished is not None, "el envío no terminó a tiempo"
    return {"results": results, "skipped": skipped, "finished": finished}


def test_broadcast_to_two_servers(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    log = AppLog(bus)
    runner = BroadcastRunner(bus, log)
    sessions = [_connected_session(ssh_server, bus, log), _connected_session(ssh_server, bus, log)]

    outcome = _run_and_collect(runner, bus, sessions, ["echo uno", "echo dos"], stop_on_failure=False)

    assert outcome["finished"].done == 4
    assert outcome["finished"].failed == 0
    assert outcome["finished"].skipped == 0
    assert len(outcome["results"]) == 4
    assert all(result.ok for result in outcome["results"])


def test_stop_on_failure_excludes_server(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    log = AppLog(bus)
    runner = BroadcastRunner(bus, log)
    session = _connected_session(ssh_server, bus, log)

    outcome = _run_and_collect(
        runner, bus, [session], ["echo uno", "esto fail", "echo nunca"], stop_on_failure=True
    )

    assert outcome["finished"].done == 2
    assert outcome["finished"].failed == 1
    assert outcome["finished"].skipped == 1
    assert len(outcome["skipped"]) == 1
    assert "nunca" not in ssh_server.exec_commands
    assert "esto fail" in ssh_server.exec_commands


def test_disconnected_server_reports_error(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    log = AppLog(bus)
    runner = BroadcastRunner(bus, log)
    session = _disconnected_session(ssh_server, bus, log)

    outcome = _run_and_collect(runner, bus, [session], ["echo x"], stop_on_failure=True)

    assert outcome["finished"].done == 1
    assert outcome["finished"].failed == 1
    assert outcome["results"][0].error == "Sin conexión SSH"


def test_templates_are_rendered_per_server(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    log = AppLog(bus)
    runner = BroadcastRunner(bus, log)
    session = _connected_session(ssh_server, bus, log)

    _run_and_collect(runner, bus, [session], ["echo host={host} user={user} port={port}"], stop_on_failure=False)

    rendered = f"echo host=127.0.0.1 user=tester port={ssh_server.port}"
    assert rendered in ssh_server.exec_commands


def test_broadcast_requires_targets_and_commands(ssh_server: SSHTestServer) -> None:
    bus = EventBus()
    runner = BroadcastRunner(bus, AppLog(bus))
    with pytest.raises(ValueError):
        runner.start([], ["echo x"])
    with pytest.raises(ValueError):
        runner.start([_disconnected_session(ssh_server, bus, AppLog(bus))], [])
