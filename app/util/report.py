"""Exportación de informes de escaneo y de comandos a CSV o JSON."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from ..models import ExecResult, ScanResult

SCAN_HEADERS = ["host", "port", "estado", "ssh", "software", "latencia_ms", "error"]
EXEC_HEADERS = ["host", "port", "comando", "codigo", "duracion_ms", "estado", "salida", "errores"]


def _rows_for_scan(results: Iterable[ScanResult]) -> list[dict]:
    rows = []
    for result in results:
        rows.append(
            {
                "host": result.host,
                "port": result.port,
                "estado": result.state,
                "ssh": "sí" if result.is_ssh else ("no" if result.ok else ""),
                "software": result.product,
                "latencia_ms": f"{result.latency_ms:.1f}" if result.latency_ms is not None else "",
                "error": result.error,
            }
        )
    return rows


def _rows_for_exec(results: Iterable[ExecResult]) -> list[dict]:
    rows = []
    for result in results:
        if result.ok:
            state = "OK"
        elif result.error:
            state = "Error"
        else:
            state = "Fallo"
        rows.append(
            {
                "host": result.host,
                "port": result.port,
                "comando": result.command,
                "codigo": result.exit_code if result.exit_code is not None else "",
                "duracion_ms": f"{result.duration_ms:.0f}",
                "estado": state,
                "salida": result.stdout.strip(),
                "errores": (result.stderr or result.error).strip(),
            }
        )
    return rows


def _write(path: Path, headers: list[str], rows: list[dict]) -> int:
    if path.suffix.lower() == ".json":
        path.write_text(
            json.dumps({"version": 1, "resultados": rows}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return len(rows)


def export_scan(path: str | Path, results: Iterable[ScanResult]) -> int:
    """Exporta resultados del escáner. Devuelve el número de filas escritas."""
    return _write(Path(path), SCAN_HEADERS, _rows_for_scan(results))


def export_exec(path: str | Path, results: Iterable[ExecResult]) -> int:
    """Exporta resultados de comandos. Devuelve el número de filas escritas."""
    return _write(Path(path), EXEC_HEADERS, _rows_for_exec(results))
