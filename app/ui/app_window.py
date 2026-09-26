"""Ventana principal de Patente."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from .. import config
from ..events import (
    BroadcastFinished,
    BroadcastStarted,
    EventBus,
    ScanFinished,
    ScanStarted,
    ServersChanged,
    SessionChanged,
    StatusEvent,
)
from ..inventory import Inventory
from ..log import AppLog
from ..scanner import Scanner
from ..snippets import Snippets
from ..ssh.broadcast import BroadcastRunner
from ..ssh.manager import ConnectionManager
from . import theme as theme_module
from .broadcast_panel import BroadcastPanel
from .connect_dialog import ConnectDialog
from .log_panel import LogPanel
from .preferences_panel import PreferencesPanel
from .scan_panel import ScanPanel
from .servers_panel import ServersPanel
from .shell_panel import ShellPanel

_TEXT_DIM = (120, 126, 136)
_ACCENT = (60, 120, 200)


class PatenteApp:
    """Estado global y ciclo de vida de la aplicación."""

    def __init__(self) -> None:
        self.settings = config.load_settings()
        self.bus = EventBus()
        self.log = AppLog(self.bus)
        self.inventory = Inventory(bus=self.bus, log=self.log)
        self.scanner = Scanner(self.bus, self.log)
        self.connections = ConnectionManager(self.inventory, self.bus, self.log, self.settings)
        self.broadcast = BroadcastRunner(self.bus, self.log)
        self.snippets = Snippets()
        self.scan_panel = ScanPanel(self)
        self.servers_panel = ServersPanel(self)
        self.broadcast_panel = BroadcastPanel(self)
        self.shell_panel = ShellPanel(self)
        self.log_panel = LogPanel(self)
        self.connect_dialog = ConnectDialog(self)
        self.preferences_panel = PreferencesPanel(self)
        self._status = "Listo"
        self._shell_menu_items: list[str] = []

    # --- ciclo de vida ---

    def run(self, render_frames: int | None = None) -> None:
        dpg.create_context()
        self._load_font()
        dpg.bind_theme(theme_module.build(self.settings.get("ui", {}).get("theme", theme_module.DARK)))
        self._build_ui()
        dpg.create_viewport(
            title=f"{config.APP_TITLE} · Escáner de red y cliente SSH",
            width=1280,
            height=820,
            min_width=980,
            min_height=620,
        )
        dpg.setup_dearpygui()
        dpg.set_primary_window("primary_window", True)
        dpg.show_viewport()
        self.connections.start()
        if render_frames is not None:
            for _ in range(render_frames):
                self._on_frame(None, None)
                dpg.render_dearpygui_frame()
        else:
            if hasattr(dpg, "set_render_callback"):
                dpg.set_render_callback(self._on_frame)
            else:
                self._schedule_tick()
            dpg.start_dearpygui()
        self._shutdown()

    def _shutdown(self) -> None:
        if self.scanner.running:
            self.scanner.stop()
        if self.broadcast.running:
            self.broadcast.stop()
        self.connections.stop()
        dpg.destroy_context()

    def _schedule_tick(self) -> None:
        self._on_frame(None, None)
        dpg.set_frame_callback(dpg.get_frame_count() + 1, lambda *_: self._schedule_tick())

    def _load_font(self) -> None:
        font_path = config.FONTS_DIR / "DejaVuSansMono.ttf"
        if not font_path.exists():
            self.log.warn(f"No se encontró la fuente {font_path}; se usará la predeterminada")
            return
        size = int(self.settings.get("ui", {}).get("font_size", 15))
        with dpg.font_registry():
            font = dpg.add_font(str(font_path), size)
        dpg.bind_font(font)

    # --- interfaz ---

    def _build_ui(self) -> None:
        # Ventana principal: el tablero de servidores con menú y barra de acciones.
        with dpg.window(tag="primary_window"):
            self._build_menu_bar()
            self._build_toolbar()
            self.servers_panel.build()
            self._build_status_bar()

        # Ventanas secundarias: se abren cuando hacen falta.
        with dpg.window(tag="win_scan", label="Escáner", show=False, width=1080, height=740, pos=[90, 70]):
            self.scan_panel.build()
        with dpg.window(
            tag="win_broadcast",
            label="Comandos",
            show=False,
            width=1220,
            height=800,
            pos=[70, 55],
        ):
            self.broadcast_panel.build()
        with dpg.window(tag="win_log", label="Registro", show=False, width=940, height=620, pos=[220, 160]):
            self.log_panel.build()

        self.servers_panel.build_dialogs()
        self.scan_panel.build_dialogs()
        self.broadcast_panel.build_dialogs()
        self.shell_panel.build_dialogs()
        self.connect_dialog.build()
        self.preferences_panel.build()
        self._build_about()
        self._register_shortcuts()
        self._sync_theme_menu()
        self.refresh_shell_menu()
        self._refresh_counts()

    def _register_shortcuts(self) -> None:
        """Atajos de teclado (F1..F5), si la versión de DearPyGui los soporta."""
        if not hasattr(dpg, "add_key_press_handler"):
            return
        shortcuts = (
            (getattr(dpg, "mvKey_F1", None), lambda *_: dpg.configure_item("about_modal", show=True)),
            (getattr(dpg, "mvKey_F2", None), lambda *_: self.show_window("win_scan")),
            (getattr(dpg, "mvKey_F3", None), lambda *_: self.show_window("win_broadcast")),
            (getattr(dpg, "mvKey_F4", None), lambda *_: self.show_window("win_log")),
            (getattr(dpg, "mvKey_F5", None), lambda *_: self.settings_panel_open()),
        )
        for key, callback in shortcuts:
            if key is None:
                continue
            try:
                dpg.add_key_press_handler(key=key, callback=callback)
            except Exception:
                return

    def settings_panel_open(self) -> None:
        self.preferences_panel.open()

    def set_theme(self, name: str) -> None:
        """Aplica y guarda el tema indicado ('oscuro' o 'claro')."""
        name = theme_module.LIGHT if str(name).lower() == theme_module.LIGHT else theme_module.DARK
        self.settings.setdefault("ui", {})["theme"] = name
        dpg.bind_theme(theme_module.build(name))
        config.save_settings(self.settings)
        self._sync_theme_menu()
        self.log.info(f"Tema aplicado: {name}")

    def _sync_theme_menu(self) -> None:
        current = str(self.settings.get("ui", {}).get("theme", theme_module.DARK)).lower()
        for value, tag in ((theme_module.DARK, "menu_theme_dark"), (theme_module.LIGHT, "menu_theme_light")):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, value == current)

    def _build_about(self) -> None:
        with dpg.window(
            tag="about_modal",
            label="Acerca de Patente",
            modal=True,
            show=False,
            width=580,
            height=290,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_text(f"{config.APP_TITLE} v{config.APP_VERSION}", color=_ACCENT)
            dpg.add_text("Escáner de red y cliente SSH con interfaz gráfica.", color=_TEXT_DIM)
            dpg.add_separator()
            dpg.add_text(
                "Flujo de trabajo: escanea la red, añade los servidores al inventario, "
                "conéctalos y abre una shell por servidor o envía comandos a muchos a la vez.",
                wrap=550,
            )
            dpg.add_text(
                "Atajos: F1 Acerca de · F2 Escáner · F3 Comandos · F4 Registro · F5 Preferencias",
                color=_TEXT_DIM,
                wrap=550,
            )
            dpg.add_text(
                "Ajustes: menú Ver → Preferencias (se guardan en settings.json).",
                color=_TEXT_DIM,
                wrap=550,
            )
            dpg.add_text(f"Registro: {self.log.path}", color=_TEXT_DIM, wrap=550)
            dpg.add_spacer(height=8)
            dpg.add_button(
                label="Cerrar",
                callback=lambda *_: dpg.configure_item("about_modal", show=False),
                width=120,
            )

    def _build_menu_bar(self) -> None:
        servers = self.servers_panel
        shells = self.shell_panel
        with dpg.menu_bar():
            with dpg.menu(label="Archivo"):
                dpg.add_menu_item(label="Añadir servidor…", callback=servers.open_add_dialog)
                dpg.add_menu_item(label="Importar…", callback=lambda *_: dpg.show_item("srv_import_dialog"))
                dpg.add_menu_item(label="Exportar…", callback=lambda *_: dpg.show_item("srv_export_dialog"))
                dpg.add_separator()
                dpg.add_menu_item(label="Salir", callback=lambda *_: dpg.stop_dearpygui())
            with dpg.menu(label="Servidores"):
                dpg.add_menu_item(label="Conectar seleccionados", callback=servers.connect_selected)
                dpg.add_menu_item(label="Conectar activos", callback=servers.connect_active)
                dpg.add_menu_item(label="Desconectar seleccionados", callback=servers.disconnect_selected)
                dpg.add_menu_item(label="Desconectar todo", callback=servers.disconnect_all)
                dpg.add_separator()
                dpg.add_menu_item(
                    label="Activar seleccionados",
                    callback=lambda *_: servers.set_enabled_selected(True),
                )
                dpg.add_menu_item(
                    label="Desactivar seleccionados",
                    callback=lambda *_: servers.set_enabled_selected(False),
                )
                dpg.add_menu_item(label="Eliminar seleccionados…", callback=servers.delete_selected)
                dpg.add_separator()
                dpg.add_menu_item(label="Seleccionar todos", callback=lambda *_: servers.select_all(True))
                dpg.add_menu_item(label="Deseleccionar todos", callback=lambda *_: servers.select_all(False))
            with dpg.menu(label="Shells"):
                dpg.add_menu_item(label="Abrir en seleccionados", callback=shells.open_selected)
                dpg.add_menu_item(label="Abrir en activos", callback=shells.open_active)
                dpg.add_separator()
                dpg.add_menu(label="Ventanas abiertas", tag="menu_shell_windows")
                dpg.add_menu_item(label="Ocultar todas las ventanas", callback=shells.close_all_windows)
            with dpg.menu(label="Enviar"):
                dpg.add_menu_item(
                    label="Comandos a muchos servidores…",
                    callback=lambda *_: self.show_window("win_broadcast"),
                )
                dpg.add_menu_item(label="Escáner de red…", callback=lambda *_: self.show_window("win_scan"))
            with dpg.menu(label="Ver"):
                with dpg.menu(label="Tema"):
                    dpg.add_menu_item(
                        label=theme_module.DARK.capitalize(),
                        tag="menu_theme_dark",
                        check=True,
                        callback=lambda *_: self.set_theme(theme_module.DARK),
                    )
                    dpg.add_menu_item(
                        label=theme_module.LIGHT.capitalize(),
                        tag="menu_theme_light",
                        check=True,
                        callback=lambda *_: self.set_theme(theme_module.LIGHT),
                    )
                dpg.add_separator()
                dpg.add_menu_item(label="Preferencias…", callback=self.settings_panel_open)
                dpg.add_separator()
                dpg.add_menu_item(label="Ventana Escáner", callback=lambda *_: self.show_window("win_scan"))
                dpg.add_menu_item(label="Ventana Comandos", callback=lambda *_: self.show_window("win_broadcast"))
                dpg.add_menu_item(label="Ventana Registro", callback=lambda *_: self.show_window("win_log"))
                dpg.add_separator()
                dpg.add_menu_item(label="Organizar en cascada", callback=self._tile_windows)
            with dpg.menu(label="Ayuda"):
                dpg.add_menu_item(
                    label="Acerca de Patente",
                    callback=lambda *_: dpg.configure_item("about_modal", show=True),
                )

    def _build_toolbar(self) -> None:
        with dpg.group(horizontal=True):
            dpg.add_button(label="Conectar", callback=self.servers_panel.connect_selected, width=110)
            dpg.add_button(label="Abrir shell", callback=self.shell_panel.open_selected, width=110)
            dpg.add_button(
                label="Comandos…",
                callback=lambda *_: self.show_window("win_broadcast"),
                width=120,
            )
            dpg.add_button(label="Escáner…", callback=lambda *_: self.show_window("win_scan"), width=110)
            dpg.add_spacer(width=18)
            dpg.add_text("Filtrar (Intro):", color=_TEXT_DIM)
            dpg.add_input_text(
                tag="srv_filter",
                width=200,
                callback=lambda *_: self.servers_panel.rebuild(),
            )
            dpg.add_spacer(width=18)
            self.shell_panel.build_main_controls()

    def _build_status_bar(self) -> None:
        with dpg.group(horizontal=True):
            dpg.add_text("Estado:", color=_TEXT_DIM)
            dpg.add_text("Listo", tag="status_bar")
            dpg.add_spacer(width=30)
            dpg.add_text("", tag="counts_bar", color=_TEXT_DIM)

    # --- fotograma ---

    def _on_frame(self, _sender, _app_data) -> None:
        for event in self.bus.drain():
            self.scan_panel.handle_event(event)
            self.servers_panel.handle_event(event)
            self.broadcast_panel.handle_event(event)
            self.shell_panel.handle_event(event)
            self.log_panel.handle_event(event)
            if isinstance(event, StatusEvent):
                self.set_status(event.message)
            elif isinstance(event, ScanStarted):
                self.set_status(f"Escaneando {event.total} objetivos…")
            elif isinstance(event, ScanFinished):
                self.set_status("Listo")
            elif isinstance(event, BroadcastStarted):
                self.set_status(f"Enviando comandos a {event.servers} servidores…")
            elif isinstance(event, BroadcastFinished):
                self.set_status("Listo")
            elif isinstance(event, ServersChanged):
                self.connections.prune({server.id for server in self.inventory.servers})
                self._refresh_counts()
            elif isinstance(event, SessionChanged):
                self._refresh_counts()
        self.shell_panel.tick()

    # --- ventanas ---

    def show_window(self, tag: str) -> None:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=True)
            dpg.focus_item(tag)

    def refresh_shell_menu(self) -> None:
        """Reconstruye la lista de ventanas de shell del menú Shells."""
        if not dpg.does_item_exist("menu_shell_windows"):
            return
        for tag in self._shell_menu_items:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._shell_menu_items.clear()
        window_ids = self.shell_panel.window_ids()
        if not window_ids:
            item = dpg.add_menu_item(
                label="(sin ventanas de shell)",
                parent="menu_shell_windows",
                enabled=False,
            )
            self._shell_menu_items.append(item)
            return
        for server_id in window_ids:
            item = dpg.add_menu_item(
                label=self.shell_panel.window_title(server_id),
                parent="menu_shell_windows",
                callback=lambda *_, sid=server_id: self.shell_panel.show_window(sid),
            )
            self._shell_menu_items.append(item)

    def _tile_windows(self, *_args) -> None:
        tags = ["win_scan", "win_broadcast", "win_log"] + [
            f"win_shell::{server_id}" for server_id in self.shell_panel.window_ids()
        ]
        index = 0
        for tag in tags:
            if dpg.does_item_exist(tag) and dpg.is_item_shown(tag):
                dpg.set_item_pos(tag, [70 + 30 * index, 60 + 26 * index])
                index += 1
        self.log.info(f"Ventanas: {index} ventanas organizadas en cascada")

    # --- utilidades ---

    def set_status(self, message: str) -> None:
        self._status = message
        if dpg.does_item_exist("status_bar"):
            dpg.set_value("status_bar", message)

    def _refresh_counts(self) -> None:
        total, active = self.inventory.counts()
        connected = self.connections.connected_count()
        if dpg.does_item_exist("counts_bar"):
            dpg.set_value(
                "counts_bar",
                f"Servidores: {total} · Activos: {active} · Conectados: {connected}",
            )

    def save_settings(self) -> None:
        config.save_settings(self.settings)
