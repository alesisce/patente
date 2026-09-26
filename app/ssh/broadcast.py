"""Envío masivo de comandos a muchas sesiones SSH en paralelo."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from ..events import (
    BroadcastFinished,
    BroadcastProgress,
    BroadcastResult,
    BroadcastServerSkipped,
    BroadcastStarted,
    EventBus,
)
from ..log import AppLog
from ..util.templating import render_template
from .session import SSHSession


class BroadcastRunner:
    """Ejecuta una lista de comandos en cada sesión, en paralelo.

    Cada servidor recibe sus comandos en orden, uno detrás de otro; el
    paralelismo es entre servidores. Si `stop_on_failure` está activo, un
    servidor que falle deja de recibir el resto de comandos.
    """

    def __init__(self, bus: EventBus, log: AppLog) -> None:
        self.bus = bus
        self.log = log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        sessions: Iterable[SSHSession],
        commands: list[str],
        timeout: float = 30.0,
        concurrency: int = 8,
        stop_on_failure: bool = True,
    ) -> None:
        sessions = list(sessions)
        if self.running:
            raise RuntimeError("Ya hay un envío en marcha")
        if not sessions:
            raise ValueError("No hay servidores destino")
        if not commands:
            raise ValueError("No hay comandos que enviar")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(sessions, list(commands), float(timeout), max(1, int(concurrency)), bool(stop_on_failure)),
            name="patente-broadcast",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- hilo orquestador ---

    def _run(
        self,
        sessions: list[SSHSession],
        commands: list[str],
        timeout: float,
        concurrency: int,
        stop_on_failure: bool,
    ) -> None:
        planned = len(sessions) * len(commands)
        self.bus.publish(BroadcastStarted(total=planned, servers=len(sessions), commands=len(commands)))
        self.log.info(
            f"Envío masivo: {len(commands)} comandos a {len(sessions)} servidores "
            f"(paralelo {min(concurrency, len(sessions))}, timeout {timeout:g}s)"
        )
        state = {"done": 0, "skipped": 0, "failed": 0}
        lock = threading.Lock()
        executor = ThreadPoolExecutor(
            max_workers=min(concurrency, len(sessions)), thread_name_prefix="patente-broadcast"
        )
        try:
            futures = [
                executor.submit(
                    self._run_server,
                    session,
                    commands,
                    timeout,
                    stop_on_failure,
                    planned,
                    state,
                    lock,
                )
                for session in sessions
            ]
            for future in futures:
                try:
                    future.result()
                except Exception as exc:  # protección: el pool nunca debe romperse
                    self.log.error(f"Envío masivo: error inesperado ({exc.__class__.__name__}): {exc}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            stopped = self._stop.is_set()
            with lock:
                summary = dict(state)
            self.bus.publish(
                BroadcastFinished(
                    done=summary["done"],
                    total=planned,
                    skipped=summary["skipped"],
                    failed=summary["failed"],
                    stopped=stopped,
                )
            )
            self.log.info(
                f"Envío masivo {'detenido' if stopped else 'finalizado'}: "
                f"{summary['done']} resultados, {summary['failed']} fallos, "
                f"{summary['skipped']} comandos omitidos"
            )

    def _run_server(
        self,
        session: SSHSession,
        commands: list[str],
        timeout: float,
        stop_on_failure: bool,
        planned: int,
        state: dict,
        lock: threading.Lock,
    ) -> None:
        server = session.server
        for index, command in enumerate(commands):
            if self._stop.is_set():
                return
            resolved = render_template(
                command,
                host=server.host,
                port=server.port,
                user=session.username,
                group=server.group,
            )
            result = session.run(resolved, timeout=timeout)
            with lock:
                state["done"] += 1
                if not result.ok:
                    state["failed"] += 1
                snapshot = dict(state)
            self.bus.publish(BroadcastResult(result=result, command_index=index, command_count=len(commands)))
            self.bus.publish(
                BroadcastProgress(
                    done=snapshot["done"],
                    total=planned,
                    skipped=snapshot["skipped"],
                    failed=snapshot["failed"],
                )
            )
            if stop_on_failure and not result.ok:
                remaining = len(commands) - index - 1
                if remaining > 0:
                    with lock:
                        state["skipped"] += remaining
                        snapshot = dict(state)
                    self.bus.publish(
                        BroadcastServerSkipped(
                            label=server.label,
                            remaining=remaining,
                            reason=result.error or f"código de salida {result.exit_code}",
                        )
                    )
                    self.bus.publish(
                        BroadcastProgress(
                            done=snapshot["done"],
                            total=planned,
                            skipped=snapshot["skipped"],
                            failed=snapshot["failed"],
                        )
                    )
                    self.log.warn(
                        f"Envío masivo: {server.label} excluido tras fallar "
                        f"({remaining} comandos no enviados)"
                    )
                return
