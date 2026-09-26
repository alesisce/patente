"""Ventana de comandos: servidores conectados arriba, comando abajo."""

from __future__ import annotations

import itertools

import dearpygui.dearpygui as dpg

from ..events import (
    BroadcastFinished,
    BroadcastProgress,
    BroadcastResult,
    BroadcastServerSkipped,
    BroadcastStarted,
    ServersChanged,
    SessionChanged,
)
from ..models import ExecResult
from ..ssh.session import CONNECTED
from ..util import report
from ..util.commands import find_dangerous
from ..util.templating import render_template

_TEXT_DIM = (120, 126, 136)
_OK_COLOR = (45, 170, 110)
_FAIL_COLOR = (220, 80, 80)
_WARN_COLOR = (200, 150, 40)
_SKIP_COLOR = (175, 125, 70)


class BroadcastPanel:
    """Selecciona servidores conectados y envía un comando a todos a la vez."""

    def __init__(self, app) -> None:
        self.app = app
        self._checked: set[str] = set()
        self._known_connected: set[str] = set()
        self._results: dict[str, ExecResult] = {}
        self._counter = itertools.count(1)
        self._history: list[str] = []
        self._pending_plan: dict | None = None
        self._snippet_command = ""

    # --- construcción ---

    def build(self) -> None:
        broadcast = self.app.settings["broadcast"]

        with dpg.group(horizontal=True):
            dpg.add_button(label="Todos", callback=lambda *_: self._select_all(True), width=80)
            dpg.add_button(label="Ninguno", callback=lambda *_: self._select_all(False), width=90)
            dpg.add_spacer(width=12)
            dpg.add_button(label="Abrir shell en seleccionados", callback=self._on_open_shell_selected)
            dpg.add_spacer(width=12)
            dpg.add_text("", tag="bc_targets_info", color=_TEXT_DIM)

        with dpg.table(
            tag="bc_targets_table",
            header_row=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            height=170,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            scrollY=True,
        ):
            dpg.add_table_column(label="Enviar", width_fixed=True, init_width_or_weight=60)
            dpg.add_table_column(label="Servidor", init_width_or_weight=1.6)
            dpg.add_table_column(label="Usuario", init_width_or_weight=1.0)
            dpg.add_table_column(label="Grupo", init_width_or_weight=1.0)
            dpg.add_table_column(label="Shell", width_fixed=True, init_width_or_weight=70)

        with dpg.group(horizontal=True):
            dpg.add_text("Comando:", color=_TEXT_DIM)
            dpg.add_input_text(
                tag="bc_command",
                width=-320,
                hint="p. ej. uptime   ·   variables {host}, {user}, {port}, {group}",
                on_enter=True,
                callback=self._on_command_enter,
            )
            dpg.add_button(label="Enviar", tag="bc_send_btn", callback=self._on_send, width=110)
            dpg.add_button(label="Detener", tag="bc_stop_btn", callback=self._on_stop, enabled=False, width=100)

        with dpg.collapsing_header(label="Opciones avanzadas", default_open=False):
            with dpg.group(horizontal=True):
                dpg.add_text("Timeout (s):", color=_TEXT_DIM)
                dpg.add_input_float(
                    tag="bc_timeout",
                    default_value=broadcast["timeout"],
                    width=90,
                    min_value=1.0,
                    max_value=3600.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.0f",
                )
                dpg.add_spacer(width=14)
                dpg.add_text("Paralelo:", color=_TEXT_DIM)
                dpg.add_input_int(
                    tag="bc_concurrency",
                    default_value=broadcast["concurrency"],
                    width=100,
                    min_value=1,
                    max_value=64,
                    min_clamped=True,
                    max_clamped=True,
                )
                dpg.add_spacer(width=14)
                dpg.add_checkbox(
                    tag="bc_stop_on_failure",
                    label="Excluir servidor si falla",
                    default_value=broadcast["stop_on_failure"],
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Historial:", color=_TEXT_DIM)
                dpg.add_combo(tag="bc_history", items=[], width=420, callback=self._on_history)
                dpg.add_spacer(width=12)
                dpg.add_button(label="Vista previa", callback=self._on_preview, width=130)
                dpg.add_button(label="Limpiar resultados", callback=self._on_clear, width=160)
                dpg.add_button(
                    label="Exportar resultados…",
                    callback=lambda *_: dpg.show_item("bc_export_dialog"),
                    width=170,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Favoritos:", color=_TEXT_DIM)
                dpg.add_combo(tag="bc_favorites", items=[], width=420, callback=self._on_favorite_selected)
                dpg.add_spacer(width=12)
                dpg.add_button(label="Guardar…", callback=self._on_save_favorite, width=130)
                dpg.add_button(label="Borrar", callback=self._on_delete_favorite, width=100)

        dpg.add_progress_bar(tag="bc_progress", default_value=0.0, width=-1, overlay="Sin envío")
        with dpg.group(horizontal=True):
            dpg.add_text("Estado:", color=_TEXT_DIM)
            dpg.add_text("Listo", tag="bc_status")

        with dpg.table(
            tag="bc_table",
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
            dpg.add_table_column(label="", width_fixed=True, init_width_or_weight=40)
            dpg.add_table_column(label="Servidor", init_width_or_weight=1.3)
            dpg.add_table_column(label="Comando", init_width_or_weight=1.8)
            dpg.add_table_column(label="Código", width_fixed=True, init_width_or_weight=70)
            dpg.add_table_column(label="Duración", width_fixed=True, init_width_or_weight=90)
            dpg.add_table_column(label="Estado", width_fixed=True, init_width_or_weight=90)
            dpg.add_table_column(label="Resumen", init_width_or_weight=2.0)

        self.refresh_targets()
        self._refresh_favorites()

    def build_dialogs(self) -> None:
        """Ventana de detalle y modales (se crean en la raíz de la interfaz)."""
        with dpg.window(
            tag="win_result",
            label="Detalle del resultado",
            show=False,
            width=860,
            height=520,
            pos=[260, 190],
        ):
            dpg.add_text("", tag="bc_detail_title", color=_TEXT_DIM, wrap=800)
            with dpg.tab_bar():
                with dpg.tab(label="Salida"):
                    dpg.add_input_text(tag="bc_detail_out", multiline=True, readonly=True, width=-1, height=350)
                with dpg.tab(label="Errores"):
                    dpg.add_input_text(tag="bc_detail_err", multiline=True, readonly=True, width=-1, height=350)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Copiar salida", callback=lambda *_: self._copy("bc_detail_out"), width=130)
                dpg.add_button(label="Copiar errores", callback=lambda *_: self._copy("bc_detail_err"), width=130)

        with dpg.window(
            tag="bc_preview_modal",
            label="Vista previa",
            modal=True,
            show=False,
            width=780,
            height=460,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_text("", tag="bc_preview_info", color=_TEXT_DIM)
            dpg.add_input_text(tag="bc_preview_text", multiline=True, readonly=True, width=-1, height=330)
            dpg.add_text("", tag="bc_preview_warn", color=_WARN_COLOR, wrap=740)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Cerrar",
                    callback=lambda *_: dpg.configure_item("bc_preview_modal", show=False),
                    width=130,
                )

        with dpg.window(
            tag="bc_danger_modal",
            label="Confirmar comando peligroso",
            modal=True,
            show=False,
            width=580,
            height=240,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_text("Se ha detectado un comando potencialmente peligroso:", color=_WARN_COLOR)
            dpg.add_text("", tag="bc_danger_text", wrap=550)
            dpg.add_text("", tag="bc_danger_info", color=_TEXT_DIM)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Enviar de todas formas", callback=self._on_confirm_danger, width=200)
                dpg.add_button(label="Cancelar", callback=self._on_cancel_danger, width=120)

        with dpg.window(
            tag="bc_save_snippet_modal",
            label="Guardar favorito",
            modal=True,
            show=False,
            width=580,
            height=240,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_text("Comando:", color=_TEXT_DIM)
            dpg.add_text("", tag="bc_snippet_command", wrap=550)
            dpg.add_input_text(tag="bc_snippet_name", hint="Nombre del favorito", width=-1)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Guardar", callback=self._on_save_snippet_ok, width=130)
                dpg.add_button(
                    label="Cancelar",
                    callback=lambda *_: dpg.configure_item("bc_save_snippet_modal", show=False),
                    width=120,
                )

        with dpg.file_dialog(
            tag="bc_export_dialog",
            label="Exportar resultados de comandos",
            show=False,
            callback=self._on_export,
            width=720,
            height=460,
            default_filename="patente_comandos.csv",
        ):
            dpg.add_file_extension(".csv")
            dpg.add_file_extension(".json")

    # --- eventos ---

    def handle_event(self, event) -> None:
        if isinstance(event, BroadcastStarted):
            self._clear_rows()
            dpg.set_value("bc_progress", 0.0)
            dpg.configure_item("bc_progress", overlay=f"0/{event.total}")
            dpg.set_value("bc_status", f"Enviando a {event.servers} servidores…")
            dpg.configure_item("bc_send_btn", enabled=False)
            dpg.configure_item("bc_stop_btn", enabled=True)
        elif isinstance(event, BroadcastResult):
            self._add_result_row(event.result)
        elif isinstance(event, BroadcastProgress):
            total = event.total or 1
            fraction = (event.done + event.skipped) / total
            dpg.set_value("bc_progress", min(1.0, fraction))
            dpg.configure_item(
                "bc_progress",
                overlay=f"{event.done + event.skipped}/{event.total} ({int(fraction * 100)}%)",
            )
            dpg.set_value(
                "bc_status",
                f"{event.done} resultados · fallos: {event.failed} · omitidos: {event.skipped}",
            )
        elif isinstance(event, BroadcastServerSkipped):
            self._add_skipped_row(event.label, event.remaining, event.reason)
        elif isinstance(event, BroadcastFinished):
            dpg.configure_item("bc_send_btn", enabled=True)
            dpg.configure_item("bc_stop_btn", enabled=False)
            dpg.set_value(
                "bc_status",
                f"Terminado: {event.done} resultados · {event.failed} fallos · {event.skipped} omitidos",
            )
        elif isinstance(event, (SessionChanged, ServersChanged)):
            self.refresh_targets()

    def refresh_targets(self) -> None:
        """Reconstruye la tabla de servidores conectados."""
        if not dpg.does_item_exist("bc_targets_table"):
            return
        sessions = [
            session
            for session in self.app.connections.sessions.values()
            if session.state == CONNECTED and session.is_alive()
        ]
        sessions.sort(key=lambda session: (session.server.host, session.server.port))
        connected_ids = {session.server.id for session in sessions}
        for server_id in connected_ids - self._known_connected:
            self._checked.add(server_id)  # las conexiones nuevas entran marcadas
        self._known_connected = connected_ids
        self._checked &= connected_ids

        dpg.delete_item("bc_targets_table", children_only=True, slot=1)
        for session in sessions:
            server = session.server
            with dpg.table_row(parent="bc_targets_table"):
                dpg.add_checkbox(
                    default_value=server.id in self._checked,
                    callback=self._on_check_toggle,
                    user_data=server.id,
                )
                dpg.add_text(server.label)
                dpg.add_text(session.username or "—")
                dpg.add_text(server.group or "—")
                dpg.add_button(
                    label="shell",
                    width=60,
                    callback=self._on_open_shell_row,
                    user_data=server.id,
                )
        info = f"Conectados: {len(sessions)} · seleccionados: {len(self._checked)}"
        if not sessions:
            info += "  ·  conecta servidores desde la ventana principal"
        dpg.set_value("bc_targets_info", info)

    # --- selección ---

    def _on_check_toggle(self, _sender, app_data, user_data) -> None:
        if app_data:
            self._checked.add(user_data)
        else:
            self._checked.discard(user_data)
        self._update_info()

    def _select_all(self, value: bool) -> None:
        if value:
            self._checked = set(self._known_connected)
        else:
            self._checked.clear()
        self.refresh_targets()

    def _update_info(self) -> None:
        if dpg.does_item_exist("bc_targets_info"):
            dpg.set_value(
                "bc_targets_info",
                f"Conectados: {len(self._known_connected)} · seleccionados: {len(self._checked)}",
            )

    def _selected_sessions(self) -> list:
        sessions = []
        for server_id in self._checked:
            session = self.app.connections.find(server_id)
            if session is not None and session.state == CONNECTED and session.is_alive():
                sessions.append(session)
        sessions.sort(key=lambda session: (session.server.host, session.server.port))
        return sessions

    # --- shells ---

    def _on_open_shell_selected(self, *_args) -> None:
        sessions = self._selected_sessions()
        self.app.shell_panel.open_servers([session.server for session in sessions])

    def _on_open_shell_row(self, _sender, _app_data, user_data) -> None:
        session = self.app.connections.find(user_data)
        if session is not None:
            self.app.shell_panel.open_servers([session.server])

    # --- filas de resultados ---

    def _add_result_row(self, result: ExecResult) -> None:
        key = f"bc{next(self._counter)}"
        self._results[key] = result
        if result.ok:
            state, color = "OK", _OK_COLOR
        elif result.error:
            state, color = "Error", _FAIL_COLOR
        else:
            state, color = "Fallo", _FAIL_COLOR
        summary = result.stdout.strip() or result.stderr.strip() or result.error
        first_line = summary.splitlines()[0][:120] if summary else ""
        with dpg.table_row(parent="bc_table"):
            dpg.add_button(label="▸", width=28, callback=self._on_show_result, user_data=key)
            dpg.add_text(f"{result.host}:{result.port}")
            dpg.add_text(result.command)
            dpg.add_text(str(result.exit_code) if result.exit_code is not None else "—", color=color)
            dpg.add_text(f"{result.duration_ms:.0f} ms")
            dpg.add_text(state, color=color)
            dpg.add_text(first_line, color=_TEXT_DIM)

    def _add_skipped_row(self, label: str, remaining: int, reason: str) -> None:
        with dpg.table_row(parent="bc_table"):
            dpg.add_button(label="—", width=28, enabled=False)
            dpg.add_text(label)
            dpg.add_text(f"({remaining} comandos no enviados)")
            dpg.add_text("—")
            dpg.add_text("—")
            dpg.add_text("Omitido", color=_SKIP_COLOR)
            dpg.add_text(reason, color=_TEXT_DIM)

    def _clear_rows(self) -> None:
        if dpg.does_item_exist("bc_table"):
            # En DearPyGui las filas de una tabla viven en el slot 1.
            dpg.delete_item("bc_table", children_only=True, slot=1)
        self._results.clear()

    def _on_clear(self, *_args) -> None:
        self._clear_rows()
        dpg.set_value("bc_detail_title", "Detalle del resultado")
        dpg.set_value("bc_detail_out", "")
        dpg.set_value("bc_detail_err", "")
        dpg.set_value("bc_progress", 0.0)
        dpg.configure_item("bc_progress", overlay="Sin envío")
        dpg.set_value("bc_status", "Listo")

    def _on_show_result(self, _sender, _app_data, user_data) -> None:
        result = self._results.get(user_data)
        if result is None:
            return
        code = result.exit_code if result.exit_code is not None else "—"
        dpg.set_value(
            "bc_detail_title",
            f"{result.host}:{result.port} · {result.command} · código {code} · {result.duration_ms:.0f} ms",
        )
        dpg.set_value("bc_detail_out", result.stdout or "(sin salida)")
        dpg.set_value("bc_detail_err", result.stderr or result.error or "(sin errores)")
        self.app.show_window("win_result")

    def _copy(self, tag: str) -> None:
        text = dpg.get_value(tag)
        if not text:
            return
        try:
            dpg.set_clipboard_text(text)
            self.app.log.info("Comandos: contenido copiado al portapapeles")
        except AttributeError:
            self.app.log.warn("Comandos: el portapapeles no está disponible en esta versión")

    # --- envío ---

    def _on_command_enter(self, _sender, _app_data) -> None:
        self._on_send()

    def _collect_plan(self) -> dict | None:
        sessions = self._selected_sessions()
        if not sessions:
            self.app.log.warn("Comandos: selecciona al menos un servidor conectado")
            return None
        command = dpg.get_value("bc_command").strip()
        if not command:
            self.app.log.warn("Comandos: escribe un comando")
            return None
        timeout = float(dpg.get_value("bc_timeout"))
        concurrency = int(dpg.get_value("bc_concurrency"))
        stop_on_failure = bool(dpg.get_value("bc_stop_on_failure"))
        self.app.settings["broadcast"] = {
            "timeout": timeout,
            "concurrency": concurrency,
            "stop_on_failure": stop_on_failure,
        }
        self.app.save_settings()
        return {
            "sessions": sessions,
            "commands": [command],
            "timeout": timeout,
            "concurrency": concurrency,
            "stop_on_failure": stop_on_failure,
        }

    def _on_send(self, *_args) -> None:
        if self.app.broadcast.running:
            self.app.log.warn("Comandos: ya hay un envío en marcha")
            return
        plan = self._collect_plan()
        if plan is None:
            return
        self._pending_plan = plan
        reasons = find_dangerous(plan["commands"])
        if reasons:
            dpg.set_value("bc_danger_text", "\n".join(f"• {reason}" for reason in reasons))
            dpg.set_value(
                "bc_danger_info",
                f"Destino: {len(plan['sessions'])} servidores · comando: {plan['commands'][0]}",
            )
            dpg.configure_item("bc_danger_modal", show=True)
            return
        self._execute(plan)

    def _on_confirm_danger(self, *_args) -> None:
        dpg.configure_item("bc_danger_modal", show=False)
        plan, self._pending_plan = self._pending_plan, None
        if plan is not None:
            self._execute(plan)

    def _on_cancel_danger(self, *_args) -> None:
        self._pending_plan = None
        dpg.configure_item("bc_danger_modal", show=False)

    def _execute(self, plan: dict) -> None:
        try:
            self.app.broadcast.start(
                plan["sessions"],
                plan["commands"],
                timeout=plan["timeout"],
                concurrency=plan["concurrency"],
                stop_on_failure=plan["stop_on_failure"],
            )
        except (RuntimeError, ValueError) as exc:
            self.app.log.error(f"Comandos: {exc}")
            return
        self._remember_history(plan["commands"][0])
        dpg.set_value("bc_command", "")

    def _on_stop(self, *_args) -> None:
        if self.app.broadcast.running:
            self.app.broadcast.stop()
            dpg.set_value("bc_status", "Deteniendo…")

    # --- historial y vista previa ---

    def _remember_history(self, command: str) -> None:
        command = command.strip()
        if not command:
            return
        if command in self._history:
            self._history.remove(command)
        self._history.insert(0, command)
        del self._history[20:]
        dpg.configure_item("bc_history", items=list(self._history))

    def _on_history(self, _sender, app_data) -> None:
        if app_data:
            dpg.set_value("bc_command", app_data)

    # --- favoritos ---

    def _refresh_favorites(self) -> None:
        if dpg.does_item_exist("bc_favorites"):
            dpg.configure_item("bc_favorites", items=self.app.snippets.names())

    def _on_favorite_selected(self, _sender, app_data) -> None:
        command = self.app.snippets.get(app_data) if app_data else ""
        if command:
            dpg.set_value("bc_command", command)

    def _on_save_favorite(self, *_args) -> None:
        command = dpg.get_value("bc_command").strip()
        if not command:
            self.app.log.warn("Comandos: escribe un comando antes de guardarlo")
            return
        self._snippet_command = command
        dpg.set_value("bc_snippet_command", command)
        dpg.set_value("bc_snippet_name", "")
        dpg.configure_item("bc_save_snippet_modal", show=True)
        dpg.focus_item("bc_snippet_name")

    def _on_save_snippet_ok(self, *_args) -> None:
        name = dpg.get_value("bc_snippet_name").strip()
        if not name:
            self.app.log.warn("Comandos: el favorito necesita un nombre")
            return
        added = self.app.snippets.add(name, self._snippet_command)
        self._refresh_favorites()
        dpg.set_value("bc_favorites", name)
        dpg.configure_item("bc_save_snippet_modal", show=False)
        self.app.log.ok(f"Comandos: favorito '{name}' {'guardado' if added else 'actualizado'}")

    def _on_delete_favorite(self, *_args) -> None:
        name = dpg.get_value("bc_favorites")
        if not name:
            self.app.log.warn("Comandos: selecciona un favorito para borrarlo")
            return
        if self.app.snippets.remove(name):
            self._refresh_favorites()
            dpg.set_value("bc_favorites", "")
            self.app.log.ok(f"Comandos: favorito '{name}' borrado")

    # --- exportar ---

    def _on_export(self, _sender, app_data) -> None:
        path = app_data.get("file_path_name") if isinstance(app_data, dict) else None
        if not path:
            return
        if not self._results:
            self.app.log.warn("Comandos: no hay resultados que exportar")
            return
        try:
            count = report.export_exec(path, list(self._results.values()))
        except OSError as exc:
            self.app.log.error(f"Comandos: no se pudo exportar ({exc})")
            return
        self.app.log.ok(f"Comandos: {count} resultados exportados a {path}")

    def _on_preview(self, *_args) -> None:
        sessions = self._selected_sessions()
        if not sessions:
            self.app.log.warn("Comandos: selecciona al menos un servidor conectado")
            return
        command = dpg.get_value("bc_command").strip()
        if not command:
            self.app.log.warn("Comandos: escribe un comando")
            return
        lines = []
        for session in sessions:
            server = session.server
            resolved = render_template(
                command,
                host=server.host,
                port=server.port,
                user=session.username,
                group=server.group,
            )
            lines.append(f"{server.label}  →  {resolved}")
        dpg.set_value("bc_preview_info", f"{len(sessions)} servidores seleccionados")
        dpg.set_value("bc_preview_text", "\n".join(lines))
        reasons = find_dangerous([command])
        dpg.set_value("bc_preview_warn", ("⚠ " + "; ".join(reasons)) if reasons else "")
        dpg.configure_item("bc_preview_modal", show=True)
