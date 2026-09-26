"""Pruebas de los modelos de datos."""

from __future__ import annotations

from app.models import ScanResult, Server, parse_ssh_banner


def test_parse_banner() -> None:
    assert parse_ssh_banner("SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.5") == "OpenSSH_9.6p1 Ubuntu-3ubuntu13.5"
    assert parse_ssh_banner("SSH-2.0-dropbear_2022.83") == "dropbear_2022.83"
    assert parse_ssh_banner("") == ""


def test_server_roundtrip() -> None:
    server = Server(host="10.0.0.1", port=2222, username="root", group="lab", notes="pruebas")
    again = Server.from_dict(server.to_dict())
    assert again == server
    assert again.label == "10.0.0.1:2222"


def test_scan_result_states() -> None:
    ssh = ScanResult(host="h", port=22, ok=True, is_ssh=True, banner="SSH-2.0-OpenSSH_9.6")
    assert ssh.state == "SSH"
    assert ssh.detail == "OpenSSH_9.6"

    open_no_banner = ScanResult(host="h", port=80, ok=True, is_ssh=False)
    assert open_no_banner.state == "Puerto abierto"
    assert open_no_banner.detail == "Sin banner SSH"

    closed = ScanResult(host="h", port=22, ok=False, error="Conexión rechazada")
    assert closed.state == "Sin conexión"
    assert closed.detail == "Conexión rechazada"
