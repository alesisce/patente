"""Pruebas de exportación de informes."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.models import ExecResult, ScanResult
from app.util.report import export_exec, export_scan


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_export_scan_csv(tmp_path: Path) -> None:
    results = [
        ScanResult(host="10.0.0.1", port=22, ok=True, is_ssh=True, latency_ms=12.34, banner="SSH-2.0-OpenSSH_9.6"),
        ScanResult(host="10.0.0.2", port=22, ok=False, error="Conexión rechazada"),
        ScanResult(host="10.0.0.3", port=80, ok=True),
    ]
    path = tmp_path / "escaneo.csv"
    assert export_scan(path, results) == 3
    rows = _read_csv(path)
    assert rows[0]["host"] == "10.0.0.1"
    assert rows[0]["ssh"] == "sí"
    assert rows[0]["software"] == "OpenSSH_9.6"
    assert rows[1]["estado"] == "Sin conexión"
    assert rows[2]["ssh"] == "no"


def test_export_scan_json(tmp_path: Path) -> None:
    results = [ScanResult(host="10.0.0.1", port=22, ok=True, is_ssh=True)]
    path = tmp_path / "escaneo.json"
    assert export_scan(path, results) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["resultados"][0]["host"] == "10.0.0.1"


def test_export_exec_csv(tmp_path: Path) -> None:
    results = [
        ExecResult(server_id="a", host="10.0.0.1", port=22, command="uptime", exit_code=0, stdout="ok\n"),
        ExecResult(server_id="b", host="10.0.0.2", port=22, command="falla", exit_code=1, stderr="error\n"),
        ExecResult(server_id="c", host="10.0.0.3", port=22, command="x", error="Sin conexión SSH"),
    ]
    path = tmp_path / "comandos.csv"
    assert export_exec(path, results) == 3
    rows = _read_csv(path)
    assert rows[0]["estado"] == "OK"
    assert rows[0]["codigo"] == "0"
    assert rows[1]["estado"] == "Fallo"
    assert rows[2]["estado"] == "Error"
    assert rows[2]["errores"] == "Sin conexión SSH"


def test_export_scan_empty(tmp_path: Path) -> None:
    path = tmp_path / "vacio.csv"
    assert export_scan(path, []) == 0
    assert path.exists()
