"""Panel del escáner de red."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..events import ScanFinished, ScanHostResult, ScanProgress, ScanStarted
from ..models import ScanResult
from ..util import report
from ..util.net import MAX_TARGETS, parse_ports, parse_targets

_STATE_OK = (45, 170, 110)
_STATE_WARN = (200, 150, 40)
_STATE_ERROR = (220, 80, 80)
_TEXT_DIM = (120, 126, 136)


def _state_color(result: ScanResult) -> tuple[int, int, int]:
    if not result.ok:
        return _STATE_ERROR
    return _STATE_OK if result.is_ssh else _STATE_WARN


def _fmt_latency(result: ScanResult) -> str:
    if result.latency_ms is None:
        return "—"
    return f"{result.latency_ms:.0f} ms"


class ScanPanel:
    """Formulario de escaneo, progreso y tabla de resultados."""

    def __init__(self, app) -> None:
        self.app = app
        self.results: dict[str, ScanResult] = {}

    # --- construcción ---

    def build(self) -> None:
        scanner = self.app.settings["scanner"]
        dpg.add_text("Objetivos (IPs, CIDR, rangos, nombres):", color=_TEXT_DIM)
        dpg.add_input_text(
            tag="scan_targets",
            multiline=True,
            width=-1,
            height=80,
            tab_input=True,
            hint="192.168.1.0/24, 10.0.0.10-25, servidor.local",
        )
        with dpg.group(horizontal=True):
            dpg.add_text("Puertos:", color=_TEXT_DIM)
            dpg.add_input_text(tag="scan_ports", default_value=scanner["ports"], width=150)
            dpg.add_spacer(width=14)
            dpg.add_text("Concurrencia:", color=_TEXT_DIM)
            dpg.add_input_int(
                tag="scan_concurrency",
                default_value=scanner["concurrency"],
                width=110,
                min_value=1,
                max_value=2000,
                min_clamped=True,
                max_clamped=True,
            )
            dpg.add_spacer(width=14)
            dpg.add_text("Timeout (s):", color=_TEXT_DIM)
            dpg.add_input_float(
                tag="scan_timeout",
                default_value=scanner["connect_timeout"],
                width=90,
                min_value=0.2,
                max_value=30.0,
                min_clamped=True,
                max_clamped=True,
                format="%.1f",
            )
            dpg.add_spacer(width=18)
            dpg.add_button(label="Escanear", tag="scan_start_btn", callback=self._on_start, width=110)
            dpg.add_button(label="Detener", tag="scan_stop_btn", callback=self._on_stop, enabled=False, width=100)
            dpg.add_button(label="Limpiar", callback=self._on_clear, width=90)

        dpg.add_progress_bar(tag="scan_progress", default_value=0.0, width=-1, overlay="Sin escaneo")
        with dpg.group(horizontal=True):
            dpg.add_text("Estado:", color=_TEXT_DIM)
            dpg.add_text("Listo", tag="scan_status")
            dpg.add_spacer(width=24)
            dpg.add_text("Filtrar (Intro):", color=_TEXT_DIM)
            dpg.add_input_text(tag="scan_filter", width=220, callback=self._on_filter)
            dpg.add_spacer(width=18)
            dpg.add_button(label="Añadir seleccionados al inventario", callback=self._on_add_selected)
            dpg.add_button(label="Exportar resultados…", callback=lambda *_: dpg.show_item("scan_export_dialog"))

        with dpg.table(
            tag="scan_table",
            header_row=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            height=-1,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            scrollY=True,
        ):
            dpg.add_table_column(label="Añadir", width_fixed=True, init_width_or_weight=60)
            dpg.add_table_column(label="Host", init_width_or_weight=1.6)
            dpg.add_table_column(label="Puerto", width_fixed=True, init_width_or_weight=70)
            dpg.add_table_column(label="Estado", init_width_or_weight=1.0)
            dpg.add_table_column(label="SSH / detalle", init_width_or_weight=2.6)
            dpg.add_table_column(label="Latencia", width_fixed=True, init_width_or_weight=90)

    # --- diálogos ---

    def build_dialogs(self) -> None:
        with dpg.file_dialog(
            tag="scan_export_dialog",
            label="Exportar resultados del escaneo",
            show=False,
            callback=self._on_export,
            width=720,
            height=460,
            default_filename="patente_escaneo.csv",
        ):
            dpg.add_file_extension(".csv")
            dpg.add_file_extension(".json")

    def _on_export(self, _sender, app_data) -> None:
        path = app_data.get("file_path_name") if isinstance(app_data, dict) else None
        if not path:
            return
        if not self.results:
            self.app.log.warn("Escáner: no hay resultados que exportar")
            return
        try:
            count = report.export_scan(path, list(self.results.values()))
        except OSError as exc:
            self.app.log.error(f"Escáner: no se pudo exportar ({exc})")
            return
        self.app.log.ok(f"Escáner: {count} resultados exportados a {path}")

    # --- eventos ---

    def handle_event(self, event) -> None:
        if isinstance(event, ScanStarted):
            self.results.clear()
            self._clear_table()
            dpg.set_value("scan_progress", 0.0)
            dpg.configure_item("scan_progress", overlay=f"0/{event.total}")
            dpg.set_value("scan_status", f"Escaneando {event.total} objetivos…")
            dpg.configure_item("scan_start_btn", enabled=False)
            dpg.configure_item("scan_stop_btn", enabled=True)
        elif isinstance(event, ScanHostResult):
            result = event.result
            self.results[result.key] = result
            if self._matches(result):
                self._update_row(result)
        elif isinstance(event, ScanProgress):
            fraction = event.done / event.total if event.total else 0.0
            dpg.set_value("scan_progress", fraction)
            dpg.configure_item("scan_progress", overlay=f"{event.done}/{event.total} ({int(fraction * 100)}%)")
        elif isinstance(event, ScanFinished):
            dpg.configure_item("scan_start_btn", enabled=True)
            dpg.configure_item("scan_stop_btn", enabled=False)
            open_count = sum(1 for result in self.results.values() if result.ok)
            ssh_count = sum(1 for result in self.results.values() if result.is_ssh)
            dpg.set_value("scan_status", f"Finalizado: {open_count} abiertos, {ssh_count} con SSH")

    # --- filas ---

    def _row_tag(self, key: str) -> str:
        return f"scan_row::{key}"

    def _matches(self, result: ScanResult) -> bool:
        text = dpg.get_value("scan_filter").strip().lower() if dpg.does_item_exist("scan_filter") else ""
        if not text:
            return True
        haystack = " ".join((result.host, str(result.port), result.state, result.detail, result.error)).lower()
        return text in haystack

    def _add_row(self, result: ScanResult) -> None:
        key = result.key
        with dpg.table_row(parent="scan_table", tag=self._row_tag(key)):
            dpg.add_checkbox(tag=f"scan_add::{key}", default_value=result.is_ssh, user_data=key)
            dpg.add_text(result.host, tag=f"scan_host::{key}")
            dpg.add_text(str(result.port), tag=f"scan_port::{key}")
            dpg.add_text(result.state, tag=f"scan_state::{key}", color=_state_color(result))
            dpg.add_text(result.detail, tag=f"scan_detail::{key}")
            dpg.add_text(_fmt_latency(result), tag=f"scan_lat::{key}")

    def _update_row(self, result: ScanResult) -> None:
        key = result.key
        if not dpg.does_item_exist(self._row_tag(key)):
            self._add_row(result)
            return
        dpg.set_value(f"scan_state::{key}", result.state)
        dpg.configure_item(f"scan_state::{key}", color=_state_color(result))
        dpg.set_value(f"scan_detail::{key}", result.detail)
        dpg.set_value(f"scan_lat::{key}", _fmt_latency(result))

    def _clear_table(self) -> None:
        if dpg.does_item_exist("scan_table"):
            # En DearPyGui las filas de una tabla viven en el slot 1.
            dpg.delete_item("scan_table", children_only=True, slot=1)

    def _rebuild_table(self) -> None:
        self._clear_table()
        for result in self.results.values():
            if self._matches(result):
                self._add_row(result)

    # --- acciones ---

    def _on_start(self, *_args) -> None:
        raw = dpg.get_value("scan_targets").strip()
        if not raw:
            self.app.log.warn("Escáner: indica al menos un objetivo")
            return
        try:
            ports = parse_ports(dpg.get_value("scan_ports"))
        except ValueError as exc:
            self.app.log.error(f"Escáner: {exc}")
            return
        hosts, errors = parse_targets(raw)
        for message in errors:
            self.app.log.warn(f"Escáner: {message}")
        if not hosts:
            self.app.log.error("Escáner: no hay objetivos válidos")
            return
        targets = [(host, port) for host in hosts for port in ports]
        if len(targets) > MAX_TARGETS:
            self.app.log.error(
                f"Escáner: demasiados sondeos ({len(targets)}); reduce el rango o los puertos"
            )
            return

        concurrency = int(dpg.get_value("scan_concurrency"))
        timeout = float(dpg.get_value("scan_timeout"))
        self.app.settings["scanner"].update(
            {
                "ports": dpg.get_value("scan_ports"),
                "concurrency": concurrency,
                "connect_timeout": timeout,
            }
        )
        self.app.save_settings()
        self.app.log.info(
            f"Escáner: {len(targets)} sondeos preparados ({len(hosts)} hosts × {len(ports)} puertos)"
        )
        try:
            self.app.scanner.start(
                targets,
                concurrency=concurrency,
                connect_timeout=timeout,
                banner_timeout=max(timeout, 1.0),
            )
        except RuntimeError as exc:
            self.app.log.warn(str(exc))

    def _on_stop(self, *_args) -> None:
        if self.app.scanner.running:
            self.app.scanner.stop()
            dpg.set_value("scan_status", "Deteniendo…")

    def _on_clear(self, *_args) -> None:
        self.results.clear()
        self._clear_table()
        dpg.set_value("scan_progress", 0.0)
        dpg.configure_item("scan_progress", overlay="Sin escaneo")
        dpg.set_value("scan_status", "Listo")

    def _on_filter(self, *_args) -> None:
        self._rebuild_table()

    def _on_add_selected(self, *_args) -> None:
        selected: list[tuple[str, int]] = []
        for key, result in self.results.items():
            tag = f"scan_add::{key}"
            if result.ok and dpg.does_item_exist(tag) and dpg.get_value(tag):
                selected.append((result.host, result.port))
        if not selected:
            self.app.log.warn("Escáner: no hay resultados seleccionados para añadir")
            return
        added, skipped = self.app.inventory.add_many(selected)
        self.app.log.ok(
            f"Inventario: {added} servidores añadidos, {skipped} omitidos (duplicados o no válidos)"
        )
