"""Punto de entrada de Patente."""

from __future__ import annotations

import argparse
import sys
import time


def _run_headless_scan(args) -> int:
    """Escaneo sin interfaz gráfica; imprime resultados por consola."""
    from app.events import EventBus, ScanFinished, ScanHostResult
    from app.log import AppLog
    from app.scanner import Scanner
    from app.util.net import parse_ports, parse_targets

    hosts, errors = parse_targets(args.scan)
    for message in errors:
        print(f"[aviso] {message}")
    try:
        ports = parse_ports(args.ports)
    except ValueError as exc:
        print(f"[error] {exc}")
        return 2
    targets = [(host, port) for host in hosts for port in ports]
    if not targets:
        print("[error] No hay objetivos válidos")
        return 2

    bus = EventBus()
    log = AppLog(bus)
    scanner = Scanner(bus, log)
    print(
        f"Escaneando {len(targets)} objetivos "
        f"(concurrencia {args.concurrency}, timeout {args.timeout:g}s)…"
    )
    scanner.start(
        targets,
        concurrency=args.concurrency,
        connect_timeout=args.timeout,
        banner_timeout=max(args.timeout, 1.0),
    )
    while True:
        events = bus.drain()
        for event in events:
            if isinstance(event, ScanHostResult):
                result = event.result
                status = "SSH" if result.is_ssh else ("abierto" if result.ok else "error")
                latency = f"{result.latency_ms:.0f} ms" if result.latency_ms is not None else "—"
                print(f"{result.host}:{result.port}\t{status}\t{latency}\t{result.detail}")
            elif isinstance(event, ScanFinished):
                suffix = " (detenido)" if event.stopped else ""
                print(f"Fin: {event.done}/{event.total}{suffix}")
        if not scanner.running and not events:
            break
        time.sleep(0.03)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass
    parser = argparse.ArgumentParser(
        prog="patente",
        description="Patente: escáner de red y cliente SSH con interfaz gráfica",
    )
    parser.add_argument("--scan", metavar="OBJETIVOS", help="escaneo sin interfaz, p. ej. '192.168.1.0/24'")
    parser.add_argument("--ports", default="22", help="puertos a escanear (por defecto: 22)")
    parser.add_argument("--concurrency", type=int, default=100, help="sondeos simultáneos (por defecto: 100)")
    parser.add_argument("--timeout", type=float, default=2.0, help="tiempo de espera en segundos (por defecto: 2.0)")
    parser.add_argument("--selftest", action="store_true", help="abre la interfaz, renderiza unos fotogramas y sale")
    args = parser.parse_args(argv)

    if args.scan:
        return _run_headless_scan(args)

    try:
        import dearpygui.dearpygui as dpg  # noqa: F401
    except ImportError as exc:
        print(f"No se pudo cargar DearPyGui: {exc}")
        print()
        print("En Linux necesitas las bibliotecas gráficas del sistema. Por ejemplo:")
        print("  Debian/Ubuntu: sudo apt install libgl1 libxinerama1 libxcursor1 libxi6 libxrandr2")
        print("  Fedora:        sudo dnf install mesa-libGL libXinerama libXcursor libXi libXrandr")
        print("  Arch:          sudo pacman -S mesa libxinerama libxcursor libxi libxrandr")
        print()
        print("Después instala las dependencias con: pip install -r requirements.txt")
        return 1

    from app.ui.app_window import PatenteApp

    app = PatenteApp()
    try:
        app.run(render_frames=5 if args.selftest else None)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
