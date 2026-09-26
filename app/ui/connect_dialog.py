"""Modal para pedir usuario y contraseña al conectar por SSH."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..models import Server

_TEXT_DIM = (120, 126, 136)


class ConnectDialog:
    """Pide la credencial de conexión.

    La contraseña solo vive en memoria. Con varios servidores y "aplicar a
    todos" marcado se conectan todos con la misma; si no, se pide una por
    cada servidor.
    """

    def __init__(self, app) -> None:
        self.app = app
        self._queue: list[Server] = []
        self._last_username = ""

    # --- construcción ---

    def build(self) -> None:
        with dpg.window(
            tag="connect_modal",
            label="Conectar por SSH",
            modal=True,
            show=False,
            width=540,
            height=400,
            no_resize=True,
            no_collapse=True,
        ):
            dpg.add_text("", tag="connect_summary", wrap=510)
            dpg.add_spacer(height=8)
            dpg.add_input_text(tag="connect_user", hint="Usuario (vacío = el de cada servidor)", width=-1)
            dpg.add_input_text(tag="connect_password", hint="Contraseña", password=True, width=-1)
            dpg.add_checkbox(
                tag="connect_show",
                label="Mostrar contraseña",
                callback=self._on_toggle_show,
            )
            dpg.add_checkbox(
                tag="connect_remember",
                label="Guardar en memoria para reconectar si se cae",
                default_value=True,
            )
            dpg.add_checkbox(
                tag="connect_apply_all",
                label="Aplicar a todos los seleccionados",
                default_value=True,
                callback=self._on_toggle_apply,
            )
            dpg.add_text("La contraseña nunca se guarda en disco.", color=_TEXT_DIM)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Conectar", callback=self._on_accept, width=130)
                dpg.add_button(label="Cancelar", callback=self._on_cancel, width=120)

    # --- apertura ---

    def open(self, servers: list[Server]) -> None:
        self._queue = list(servers)
        if not self._queue:
            self.app.log.warn("SSH: no hay servidores para conectar")
            return
        default_user = self._queue[0].username or self._last_username
        dpg.set_value("connect_user", default_user)
        dpg.set_value("connect_password", "")
        dpg.set_value("connect_show", False)
        dpg.configure_item("connect_password", password=True)
        dpg.set_value("connect_remember", True)
        dpg.set_value("connect_apply_all", True)
        self._update_summary()
        dpg.configure_item("connect_modal", show=True)
        dpg.focus_item("connect_password" if default_user else "connect_user")

    # --- acciones ---

    def _on_accept(self, *_args) -> None:
        password = dpg.get_value("connect_password")
        if not password:
            self.app.log.warn("SSH: escribe la contraseña")
            return
        username = dpg.get_value("connect_user").strip()
        self._last_username = username
        remember = bool(dpg.get_value("connect_remember"))
        apply_all = bool(dpg.get_value("connect_apply_all"))

        if apply_all:
            targets = self._queue
            self._queue = []
            dpg.configure_item("connect_modal", show=False)
        else:
            targets = [self._queue.pop(0)]
            if self._queue:
                dpg.set_value("connect_password", "")
                self._update_summary()
                dpg.focus_item("connect_password")
            else:
                dpg.configure_item("connect_modal", show=False)

        entries = [(server, server.username or username, password, remember) for server in targets]
        self.app.connections.connect_many(entries)
        if len(entries) > 1:
            self.app.log.info(f"SSH: conectando {len(entries)} servidores…")

    def _on_cancel(self, *_args) -> None:
        self._queue.clear()
        dpg.configure_item("connect_modal", show=False)

    def _on_toggle_show(self, *_args) -> None:
        dpg.configure_item("connect_password", password=not dpg.get_value("connect_show"))

    def _on_toggle_apply(self, *_args) -> None:
        self._update_summary()

    def _update_summary(self) -> None:
        labels = [server.label for server in self._queue]
        if len(labels) == 1:
            text = f"Conectar {labels[0]}"
        else:
            shown = ", ".join(labels[:6]) + ("…" if len(labels) > 6 else "")
            text = f"Conectar {len(labels)} servidores: {shown}"
            if not dpg.get_value("connect_apply_all"):
                text += "\nSe pedirá la contraseña para cada servidor."
        dpg.set_value("connect_summary", text)
