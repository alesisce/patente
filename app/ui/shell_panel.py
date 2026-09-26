"""Ventanas de shells interactivas: una por servidor."""

from __future__ import annotations

import time

import dearpygui.dearpygui as dpg

from ..events import ShellClosed, ShellOpened, ShellOutput, SessionChanged
from ..ssh.session import CONNECTED
from ..util.ansi import AnsiTerminal

_TEXT_DIM = (120, 126, 136)
_OK_COLOR = (45, 170, 110)
_WARN_COLOR = (200, 150, 40)


class ShellPanel:
    """Cada shell se abre en su propia ventana; controles globales en la barra principal."""

    def __init__(self, app) -> None:
        self.app = app
        ui = app.settings.get("ui", {})
        self._max_scrollback = int(ui.get("max_scrollback", 2000))
        self._render_lines = int(ui.get("shell_render_lines", 300))
        self._terminals: dict[str, AnsiTerminal] = {}
        self._opened: set[str] = set()
        self._windows: set[str] = set()
        self._last_render: dict[str, float] = {}
        self._pending_size: set[str] = set()
        self._pending_save: str | None = None
        self._frame = 0
        self._window_seq = 0

    # --- construcción ---

    def build_main_controls(self) -> None:
        """Controles globales que viven en la barra principal de la aplicación."""
        dpg.add_checkbox(
            tag="shell_send_all",
            label="Escribir a todas",
            default_value=False,
            callback=self._on_toggle_send_all,
        )
        dpg.add_text("", tag="shell_info", color=_TEXT_DIM)

    def build_dialogs(self) -> None:
        with dpg.file_dialog(
            tag="shell_save_dialog",
            label="Guardar transcripción",
            show=False,
            callback=self._on_save_path,
            width=720,
            height=460,
            default_filename="patente_transcripcion.log",
        ):
            dpg.add_file_extension(".log")
            dpg.add_file_extension(".txt")

    def _ensure_window(self, server_id: str) -> None:
        server = self._server(server_id)
        if server is None:
            return
        self._windows.add(server_id)
        tag = f"win_shell::{server_id}"
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=True)
            dpg.focus_item(tag)
            return
        self._terminals.setdefault(server_id, AnsiTerminal(max_lines=self._max_scrollback))
        self._window_seq += 1
        offset = self._window_seq % 6
        with dpg.window(
            tag=tag,
            label=f"Shell · {server.label}",
            width=1000,
            height=690,
            pos=[150 + 28 * offset, 80 + 24 * offset],
            show=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Abrir shell", callback=self._on_open_one, user_data=server_id, width=110)
                dpg.add_button(label="Cerrar shell", callback=self._on_close_shell, user_data=server_id, width=110)
                dpg.add_button(label="Limpiar", callback=self._on_clear_shell, user_data=server_id, width=90)
                dpg.add_button(
                    label="Guardar transcripción",
                    callback=self._on_save_transcript,
                    user_data=server_id,
                    width=170,
                )
                dpg.add_button(
                    label="Copiar todo",
                    callback=self._on_copy_transcript,
                    user_data=server_id,
                    width=120,
                )
                dpg.add_text("", tag=f"shell_state::{server_id}", color=_TEXT_DIM)
            dpg.add_child_window(
                tag=f"shell_term::{server_id}",
                border=True,
                height=-120,
                horizontal_scrollbar=False,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="Ctrl+C", callback=self._on_key, user_data=(server_id, "\x03"), width=80)
                dpg.add_button(label="Ctrl+D", callback=self._on_key, user_data=(server_id, "\x04"), width=80)
                dpg.add_button(label="Ctrl+Z", callback=self._on_key, user_data=(server_id, "\x1a"), width=80)
                dpg.add_button(label="Tab", callback=self._on_key, user_data=(server_id, "\t"), width=70)
                dpg.add_input_text(
                    tag=f"shell_input::{server_id}",
                    width=-1,
                    hint="Escribe y pulsa Intro",
                    callback=self._on_input,
                    user_data=server_id,
                    on_enter=True,
                )
        self._pending_size.add(server_id)
        if dpg.does_item_exist(f"shell_input::{server_id}"):
            dpg.focus_item(f"shell_input::{server_id}")
        self.app.refresh_shell_menu()

    # --- API para menús y ventanas ---

    def window_ids(self) -> list[str]:
        return [server_id for server_id in self._windows if dpg.does_item_exist(f"win_shell::{server_id}")]

    def apply_limits(self, max_scrollback: int, render_lines: int) -> None:
        """Aplica los límites de historial de las preferencias."""
        self._max_scrollback = max(100, int(max_scrollback))
        self._render_lines = max(50, int(render_lines))
        for terminal in self._terminals.values():
            terminal.max_lines = self._max_scrollback
        self.app.log.info("Shells: límites de historial actualizados")

    def window_title(self, server_id: str) -> str:
        server = self._server(server_id)
        label = server.label if server is not None else server_id
        return f"{label} · {'abierta' if server_id in self._opened else 'cerrada'}"

    def show_window(self, server_id: str) -> None:
        self._ensure_window(server_id)

    def close_all_windows(self, *_args) -> None:
        for server_id in self.window_ids():
            dpg.configure_item(f"win_shell::{server_id}", show=False)
        self.app.log.info("Shells: ventanas ocultas (las shells siguen abiertas)")

    def open_selected(self, *_args) -> None:
        self.open_servers(self.app.servers_panel.selected_servers())

    def open_active(self, *_args) -> None:
        self.open_servers(self.app.inventory.enabled_servers)

    def open_servers(self, servers) -> None:
        """Abre shells para la lista de servidores dada (omite los no conectados)."""
        servers = [server for server in servers if server is not None]
        if not servers:
            self.app.log.warn("Shells: no hay servidores seleccionados")
            return
        self._open_many(servers)

    def _on_open_one(self, _sender, _app_data, user_data) -> None:
        server = self._server(user_data)
        if server is not None:
            self._open_many([server])

    def _open_many(self, servers) -> None:
        opened = skipped = 0
        for server in servers:
            session = self.app.connections.find(server.id)
            if session is None or session.state != CONNECTED or not session.is_alive():
                skipped += 1
                continue
            if session.open_shell():
                opened += 1
        if skipped:
            self.app.log.warn(f"Shells: {skipped} servidores omitidos por no estar conectados")
        if not opened:
            self.app.log.warn("Shells: no se abrió ninguna shell")

    def _on_close_shell(self, _sender, _app_data, user_data) -> None:
        session = self.app.connections.find(user_data)
        if session is not None:
            session.close_shell()

    # --- eventos ---

    def handle_event(self, event) -> None:
        if isinstance(event, ShellOpened):
            self._opened.add(event.server_id)
            self._ensure_window(event.server_id)
            self._update_state_text(event.server_id, "abierta", _OK_COLOR)
            self._pending_size.add(event.server_id)
            self._refresh_info()
        elif isinstance(event, ShellOutput):
            terminal = self._terminals.get(event.server_id)
            if terminal is None:
                terminal = AnsiTerminal(max_lines=self._max_scrollback)
                self._terminals[event.server_id] = terminal
            terminal.feed(event.data)
        elif isinstance(event, ShellClosed):
            self._opened.discard(event.server_id)
            reason = event.reason or "cerrada"
            self._update_state_text(event.server_id, f"shell cerrada: {reason}", _WARN_COLOR)
            self._refresh_info()
            self.app.refresh_shell_menu()
        elif isinstance(event, SessionChanged):
            self._refresh_info()

    def tick(self) -> None:
        """Renderiza lo pendiente y ajusta el tamaño del pty una vez por fotograma."""
        self._frame += 1
        now = time.monotonic()
        for server_id, terminal in list(self._terminals.items()):
            if terminal.dirty and now - self._last_render.get(server_id, 0.0) >= 0.12:
                self._render(server_id)
        for server_id in list(self._pending_size):
            if self._sync_size(server_id):
                self._pending_size.discard(server_id)
        if self._frame % 90 == 0:
            for server_id in self.window_ids():
                if dpg.is_item_shown(f"win_shell::{server_id}"):
                    self._sync_size(server_id)

    # --- interno ---

    def _server(self, server_id: str):
        return next((server for server in self.app.inventory.servers if server.id == server_id), None)

    def _update_state_text(self, server_id: str, text: str, color) -> None:
        tag = f"shell_state::{server_id}"
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, text)
            dpg.configure_item(tag, color=color)

    def _targets(self, server_id: str) -> list[str]:
        if dpg.does_item_exist("shell_send_all") and dpg.get_value("shell_send_all"):
            return list(self._opened)
        return [server_id]

    def _send(self, server_id: str, text: str) -> None:
        sent = 0
        for target in self._targets(server_id):
            session = self.app.connections.find(target)
            if session is not None and session.send_shell(text):
                sent += 1
        if sent == 0:
            self.app.log.warn("Shells: no se pudo enviar (la shell no está abierta)")

    def _on_input(self, sender, app_data, user_data) -> None:
        text = (app_data or "").strip()
        dpg.set_value(sender, "")
        if not text:
            return
        self._send(user_data, text + "\n")

    def _on_key(self, _sender, _app_data, user_data) -> None:
        server_id, sequence = user_data
        self._send(server_id, sequence)

    def _on_toggle_send_all(self, *_args) -> None:
        self._refresh_info()
        if dpg.get_value("shell_send_all"):
            self.app.log.info("Shells: lo que escribas se enviará a todas las shells abiertas")

    def _refresh_info(self) -> None:
        if not dpg.does_item_exist("shell_info"):
            return
        count = len(self._opened)
        text = f"Shells abiertas: {count}"
        if dpg.does_item_exist("shell_send_all") and dpg.get_value("shell_send_all"):
            text += f" · escribiendo a las {count}"
        dpg.set_value("shell_info", text)

    # --- limpiar, guardar y copiar ---

    def _on_clear_shell(self, _sender, _app_data, user_data) -> None:
        terminal = self._terminals.get(user_data)
        if terminal is not None:
            terminal.clear()
            self._render(user_data)

    def _transcript(self, server_id: str) -> str:
        terminal = self._terminals.get(server_id)
        return terminal.text() if terminal is not None else ""

    def _on_save_transcript(self, _sender, _app_data, user_data) -> None:
        server = self._server(user_data)
        if server is None:
            return
        self._pending_save = user_data
        dpg.configure_item(
            "shell_save_dialog",
            default_filename=f"patente_{server.host}_{server.port}.log",
        )
        dpg.show_item("shell_save_dialog")

    def _on_save_path(self, _sender, app_data) -> None:
        path = app_data.get("file_path_name") if isinstance(app_data, dict) else None
        server_id, self._pending_save = self._pending_save, None
        if not path or server_id is None:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self._transcript(server_id) + "\n")
        except OSError as exc:
            self.app.log.error(f"Shells: no se pudo guardar la transcripción ({exc})")
            return
        self.app.log.ok(f"Shells: transcripción guardada en {path}")

    def _on_copy_transcript(self, _sender, _app_data, user_data) -> None:
        text = self._transcript(user_data)
        if not text:
            return
        try:
            dpg.set_clipboard_text(text)
            self.app.log.info("Shells: transcripción copiada al portapapeles")
        except AttributeError:
            self.app.log.warn("Shells: el portapapeles no está disponible en esta versión")

    # --- renderizado ---

    def _render(self, server_id: str) -> None:
        container = f"shell_term::{server_id}"
        terminal = self._terminals.get(server_id)
        if terminal is None or not dpg.does_item_exist(container):
            return
        terminal.dirty = False
        self._last_render[server_id] = time.monotonic()
        dpg.delete_item(container, children_only=True)
        for cells in terminal.visible_lines(self._render_lines):
            segments = AnsiTerminal.segments(cells)
            if not segments:
                dpg.add_text("", parent=container)
                continue
            with dpg.group(horizontal=True, parent=container):
                for segment in segments:
                    dpg.add_text(segment.text, color=segment.fg)
        dpg.set_y_scroll(container, -1)

    def _sync_size(self, server_id: str) -> bool:
        container = f"shell_term::{server_id}"
        if not dpg.does_item_exist(container):
            return True
        width, height = dpg.get_item_rect_size(container)
        if width <= 0 or height <= 0:
            return False
        font_size = float(self.app.settings.get("ui", {}).get("font_size", 15))
        cols = max(20, int(width / (font_size * 0.62)))
        rows = max(5, int(height / (font_size * 1.4)))
        session = self.app.connections.find(server_id)
        if session is not None and session.shell_active:
            session.resize_shell(cols, rows)
        return True
