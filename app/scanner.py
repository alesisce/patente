"""Escáner de red asíncrono con detección de banner SSH."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterable

from .events import (
    EventBus,
    ScanFinished,
    ScanHostResult,
    ScanProgress,
    ScanStarted,
)
from .log import AppLog
from .models import ScanResult


def _friendly_error(exc: BaseException) -> str:
    if isinstance(exc, socket.gaierror):
        return "No se pudo resolver el nombre"
    if isinstance(exc, ConnectionRefusedError):
        return "Conexión rechazada"
    if isinstance(exc, TimeoutError):
        return "Tiempo de espera agotado"
    text = str(exc)
    return text or exc.__class__.__name__


class Scanner:
    """Escaneo TCP con concurrencia limitada.

    El trabajo ocurre en un hilo propio con su bucle asyncio; los resultados
    llegan a la interfaz mediante el bus de eventos.
    """

    def __init__(self, bus: EventBus, log: AppLog) -> None:
        self.bus = bus
        self.log = log
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        targets: Iterable[tuple[str, int]],
        concurrency: int = 100,
        connect_timeout: float = 2.0,
        banner_timeout: float = 2.0,
    ) -> None:
        if self.running:
            raise RuntimeError("Ya hay un escaneo en marcha")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_blocking,
            args=(list(targets), max(1, int(concurrency)), float(connect_timeout), float(banner_timeout)),
            name="patente-scanner",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- hilo del escáner ---

    def _run_blocking(
        self,
        targets: list[tuple[str, int]],
        concurrency: int,
        connect_timeout: float,
        banner_timeout: float,
    ) -> None:
        try:
            asyncio.run(self._run_async(targets, concurrency, connect_timeout, banner_timeout))
        except Exception as exc:  # protección: nunca debe tumbar la aplicación
            self.log.error(f"Escáner: error inesperado ({exc.__class__.__name__}): {exc}")

    async def _run_async(
        self,
        targets: list[tuple[str, int]],
        concurrency: int,
        connect_timeout: float,
        banner_timeout: float,
    ) -> None:
        total = len(targets)
        done = 0
        self.bus.publish(ScanStarted(total=total))
        self.log.info(f"Escaneo iniciado: {total} objetivos, concurrencia {concurrency}")
        semaphore = asyncio.Semaphore(concurrency)
        tasks = [
            asyncio.create_task(self._probe(host, port, semaphore, connect_timeout, banner_timeout))
            for host, port in targets
        ]
        try:
            for future in asyncio.as_completed(tasks):
                result = await future
                done += 1
                self.bus.publish(ScanHostResult(result=result))
                self.bus.publish(ScanProgress(done=done, total=total))
                if self._stop.is_set():
                    break
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            stopped = self._stop.is_set() and done < total
            self.bus.publish(ScanFinished(done=done, total=total, stopped=stopped))
            self.log.info(f"Escaneo {'detenido' if stopped else 'finalizado'}: {done}/{total}")

    async def _probe(
        self,
        host: str,
        port: int,
        semaphore: asyncio.Semaphore,
        connect_timeout: float,
        banner_timeout: float,
    ) -> ScanResult:
        async with semaphore:
            started = time.perf_counter()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=connect_timeout
                )
            except asyncio.TimeoutError:
                return ScanResult(host=host, port=port, ok=False, error="Tiempo de espera agotado")
            except OSError as exc:
                return ScanResult(host=host, port=port, ok=False, error=_friendly_error(exc))

            latency_ms = (time.perf_counter() - started) * 1000.0
            banner = ""
            try:
                raw = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=banner_timeout)
                banner = raw.decode("utf-8", errors="replace").strip()
            except asyncio.IncompleteReadError as exc:
                banner = exc.partial.decode("utf-8", errors="replace").strip()
            except (asyncio.TimeoutError, asyncio.LimitOverrunError, OSError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, asyncio.TimeoutError):
                    pass

            return ScanResult(
                host=host,
                port=port,
                ok=True,
                is_ssh=banner.startswith("SSH-"),
                latency_ms=latency_ms,
                banner=banner,
            )
