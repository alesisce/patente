"""Panel del inventario de servidores (contenido de la ventana principal)."""

from __future__ import annotations

from pathlib import Path

import dearpygui.dearpygui as dpg

from ..events import ServersChanged, SessionChanged

_TEXT_DIM = (120, 126, 136)
_STATE_LABELS = {
    "disconnected": ("Desconectado", (120, 126, 136)),
    "connecting": ("Conectando…", (200, 150, 40)),
    "reconnecting": ("Reconectando…", (215, 130, 50)),
    "connected": ("Conectado", (45, 170, 110)),
    "error": ("Error", (220, 80, 80)),
}


class ServersPanel:
    """Tabla central de servidores: exclusión, selección, estado SSH y acciones."""

    def __init__(self, app) -> None:
        self.app = app
        self._selected: set[str] = set()
        self._pending_delete: list[str] = []

    # --- construcción ---

    def build(self) -> None:
        dpg.add_text(
            "'Activo' excluye al servidor del envío masivo y de las shells; 'Sel.' sirve para las acciones por lotes.",
            tag="srv_hint",
            color=_TEXT_DIM,
        )
        with dpg.table(
            tag="srv_table",
            header_row=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            height=-40,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            scrollY=True,
        ):
            dpg.add_table_column(label="Sel.", width_fixed=True, init_width_or_weight=55)
            dpg.add_table_column(label="Activo", width_fixed=True, init_width_or_weight=60)
            dpg.add_table_column(label="Host", init_width_or_weight=1.7)
            dpg.add_table_column(label="Puerto", width_fixed=True, init_width_or_weight=70)
            dpg.add_table_column(label="Usuario", init_width_or_weight=0.9)
            dpg.add_table_column(label="Grupo", init_width_or_weight=0.9)
            dpg.add_table_column(label="SSH", width_fixed=True, init_width_or_weight=110)
            dpg.add_table_column(label="Detalle", init_width_or_weight=1.7)
            dpg.add_table_column(label="Notas", init_width_or_weight=1.2)
        self.rebuild()

    def build_dialogs(self) -> None:
        """Modales y diálogos de archivo (deben crearse en la raíz de la interfaz)."""
        with dpg.window(
            tag="srv_add_modal",
            label="Añadir servidor",
            modal=True,
            show=False,
            width=470,
            height=330,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_input_text(tag="srv_add_host", hint="Host / IP (obligatorio)", width=-1)
            dpg.add_input_text(tag="srv_add_port", hint="Puerto (22)", width=-1)
            dpg.add_input_text(tag="srv_add_user", hint="Usuario (opcional)", width=-1)
            dpg.add_input_text(tag="srv_add_group", hint="Grupo (opcional)", width=-1)
            dpg.add_input_text(tag="srv_add_notes", hint="Notas (opcional)", width=-1)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Guardar", callback=self._on_add_save, width=120)
                dpg.add_button(
                    label="Cancelar",
                    callback=lambda *_: dpg.configure_item("srv_add_modal", show=False),
                    width=120,
                )

        with dpg.window(
            tag="confirm_modal",
            label="Confirmar",
            modal=True,
            show=False,
            width=430,
            height=130,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_text("", tag="confirm_text", wrap=400)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Sí, eliminar", callback=self._on_confirm_delete, width=130)
                dpg.add_button(
                    label="Cancelar",
                    callback=lambda *_: dpg.configure_item("confirm_modal", show=False),
                    width=120,
                )

        with dpg.file_dialog(
            tag="srv_import_dialog",
            label="Importar servidores (.json o .csv)",
            show=False,
            callback=self._on_import,
            width=720,
            height=460,
        ):
            dpg.add_file_extension(".csv")
            dpg.add_file_extension(".json")

        with dpg.file_dialog(
            tag="srv_export_dialog",
            label="Exportar servidores",
            show=False,
            callback=self._on_export,
            width=720,
            height=460,
            default_filename="patente_servidores.csv",
        ):
            dpg.add_file_extension(".csv")
            dpg.add_file_extension(".json")

    # --- eventos ---

    def handle_event(self, event) -> None:
        if isinstance(event, ServersChanged) and event.reason != "enable":
            valid_ids = {server.id for server in self.app.inventory.servers}
            self._selected &= valid_ids
            self.rebuild()
        elif isinstance(event, SessionChanged):
            self._apply_state(event.server_id)

    def rebuild(self) -> None:
        if not dpg.does_item_exist("srv_table"):
            return
        if dpg.does_item_exist("srv_hint"):
            if self.app.inventory.servers:
                dpg.set_value(
                    "srv_hint",
                    "'Activo' excluye al servidor del envío masivo y de las shells; 'Sel.' sirve para las acciones por lotes.",
                )
            else:
                dpg.set_value(
                    "srv_hint",
                    "El inventario está vacío: añade un servidor (Archivo → Añadir servidor) o escanea tu red (barra superior → Escáner…).",
                )
        # En DearPyGui las filas de una tabla viven en el slot 1.
        dpg.delete_item("srv_table", children_only=True, slot=1)
        text = dpg.get_value("srv_filter").strip().lower() if dpg.does_item_exist("srv_filter") else ""
        for server in self.app.inventory.servers:
            haystack = f"{server.host}:{server.port} {server.username} {server.group} {server.notes}".lower()
            if text and text not in haystack:
                continue
            with dpg.table_row(parent="srv_table"):
                dpg.add_checkbox(
                    default_value=server.id in self._selected,
                    callback=self._on_select_toggle,
                    user_data=server.id,
                )
                dpg.add_checkbox(
                    default_value=server.enabled,
                    callback=self._on_enabled_toggle,
                    user_data=server.id,
                )
                dpg.add_text(server.host)
                dpg.add_text(str(server.port))
                dpg.add_text(server.username or "—")
                dpg.add_text(server.group or "—")
                dpg.add_text("", tag=f"srv_state::{server.id}")
                dpg.add_text("", tag=f"srv_detail::{server.id}", color=_TEXT_DIM)
                dpg.add_text(server.notes or "")
            self._apply_state(server.id)

    def _apply_state(self, server_id: str) -> None:
        session = self.app.connections.find(server_id)
        state = session.state if session is not None else "disconnected"
        detail = session.detail if session is not None else ""
        label, color = _STATE_LABELS.get(state, _STATE_LABELS["disconnected"])
        state_tag = f"srv_state::{server_id}"
        if dpg.does_item_exist(state_tag):
            dpg.set_value(state_tag, label)
            dpg.configure_item(state_tag, color=color)
        detail_tag = f"srv_detail::{server_id}"
        if dpg.does_item_exist(detail_tag):
            dpg.set_value(detail_tag, detail)

    # --- selección ---

    def _on_select_toggle(self, _sender, app_data, user_data) -> None:
        if app_data:
            self._selected.add(user_data)
        else:
            self._selected.discard(user_data)

    def _on_enabled_toggle(self, _sender, app_data, user_data) -> None:
        self.app.inventory.set_enabled([user_data], bool(app_data))

    def select_all(self, value: bool) -> None:
        if value:
            self._selected = {server.id for server in self.app.inventory.servers}
        else:
            self._selected.clear()
        self.rebuild()

    def set_enabled_selected(self, value: bool) -> None:
        if not self._selected:
            self.app.log.warn("Inventario: no hay servidores seleccionados")
            return
        changed = self.app.inventory.set_enabled(self._selected, value)
        self.app.log.info(f"Inventario: {changed} servidores {'activados' if value else 'desactivados'}")

    def selected_servers(self) -> list:
        return [server for server in self.app.inventory.servers if server.id in self._selected]

    # --- conexión ---

    def connect_selected(self, *_args) -> None:
        servers = self.selected_servers()
        if not servers:
            self.app.log.warn("SSH: no hay servidores seleccionados")
            return
        self.app.connect_dialog.open(servers)

    def connect_active(self, *_args) -> None:
        servers = self.app.inventory.enabled_servers
        if not servers:
            self.app.log.warn("SSH: no hay servidores activos en el inventario")
            return
        self.app.connect_dialog.open(servers)

    def disconnect_selected(self, *_args) -> None:
        if not self._selected:
            self.app.log.warn("SSH: no hay servidores seleccionados")
            return
        for server_id in list(self._selected):
            self.app.connections.disconnect(server_id)

    def disconnect_all(self, *_args) -> None:
        self.app.connections.disconnect_all()
        self.app.log.info("SSH: todas las sesiones desconectadas")

    # --- altas y bajas ---

    def open_add_dialog(self, *_args) -> None:
        for tag, value in (
            ("srv_add_host", ""),
            ("srv_add_port", "22"),
            ("srv_add_user", ""),
            ("srv_add_group", ""),
            ("srv_add_notes", ""),
        ):
            dpg.set_value(tag, value)
        dpg.configure_item("srv_add_modal", show=True)
        dpg.focus_item("srv_add_host")

    def _on_add_save(self, *_args) -> None:
        host = dpg.get_value("srv_add_host").strip()
        if not host:
            self.app.log.warn("Inventario: el host no puede estar vacío")
            return
        try:
            port = int(dpg.get_value("srv_add_port").strip() or "22")
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.app.log.error("Inventario: puerto no válido")
            return
        server = self.app.inventory.add(
            host,
            port,
            dpg.get_value("srv_add_user"),
            dpg.get_value("srv_add_group"),
            dpg.get_value("srv_add_notes"),
        )
        if server is None:
            self.app.log.warn(f"Inventario: {host}:{port} ya estaba en la lista")
            return
        dpg.configure_item("srv_add_modal", show=False)
        self.app.log.ok(f"Inventario: añadido {server.label}")

    def delete_selected(self, *_args) -> None:
        if not self._selected:
            self.app.log.warn("Inventario: no hay servidores seleccionados")
            return
        self._pending_delete = sorted(self._selected)
        dpg.set_value("confirm_text", f"¿Eliminar {len(self._pending_delete)} servidores del inventario?")
        dpg.configure_item("confirm_modal", show=True)

    def _on_confirm_delete(self, *_args) -> None:
        removed = self.app.inventory.remove_ids(self._pending_delete)
        self._selected -= set(self._pending_delete)
        self._pending_delete = []
        dpg.configure_item("confirm_modal", show=False)
        self.app.log.ok(f"Inventario: {removed} servidores eliminados")

    # --- importar / exportar ---

    def _on_import(self, _sender, app_data) -> None:
        path = app_data.get("file_path_name") if isinstance(app_data, dict) else None
        if not path:
            return
        try:
            added, skipped = self.app.inventory.import_file(path)
        except (OSError, ValueError) as exc:
            self.app.log.error(f"Inventario: no se pudo importar ({exc})")
            return
        self.app.log.ok(f"Inventario: importados {added}, omitidos {skipped} ({Path(path).name})")

    def _on_export(self, _sender, app_data) -> None:
        path = app_data.get("file_path_name") if isinstance(app_data, dict) else None
        if not path:
            return
        try:
            count = self.app.inventory.export_file(path)
        except OSError as exc:
            self.app.log.error(f"Inventario: no se pudo exportar ({exc})")
            return
        self.app.log.ok(f"Inventario: {count} servidores exportados a {path}")
