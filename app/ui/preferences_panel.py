"""Ventana de preferencias: escáner, SSH, comandos e interfaz."""

from __future__ import annotations

import copy

import dearpygui.dearpygui as dpg

from .. import config
from . import theme as theme_module

_TEXT_DIM = (120, 126, 136)
_OK_COLOR = (45, 170, 110)


class PreferencesPanel:
    """Editor de los ajustes guardados en settings.json."""

    def __init__(self, app) -> None:
        self.app = app

    # --- construcción ---

    def build(self) -> None:
        with dpg.window(
            tag="win_prefs",
            label="Preferencias",
            show=False,
            width=640,
            height=680,
            pos=[250, 80],
        ):
            with dpg.collapsing_header(label="Escáner", default_open=True):
                dpg.add_input_text(tag="pref_ports", label="Puertos por defecto", width=220)
                dpg.add_input_int(
                    tag="pref_concurrency",
                    label="Sondeos simultáneos",
                    width=160,
                    min_value=1,
                    max_value=2000,
                    min_clamped=True,
                    max_clamped=True,
                )
                dpg.add_input_float(
                    tag="pref_scan_timeout",
                    label="Timeout de sondeo (s)",
                    width=140,
                    min_value=0.2,
                    max_value=30.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.1f",
                )
            with dpg.collapsing_header(label="Conexiones SSH"):
                dpg.add_input_float(
                    tag="pref_connect_timeout",
                    label="Timeout de conexión (s)",
                    width=140,
                    min_value=1.0,
                    max_value=120.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.0f",
                )
                dpg.add_input_int(
                    tag="pref_keepalive",
                    label="Keepalive (s)",
                    width=140,
                    min_value=0,
                    max_value=600,
                    min_clamped=True,
                    max_clamped=True,
                )
                dpg.add_checkbox(tag="pref_auto_reconnect", label="Reconectar automáticamente si se cae")
                dpg.add_input_float(
                    tag="pref_reconnect_base",
                    label="Espera inicial de reconexión (s)",
                    width=140,
                    min_value=0.5,
                    max_value=60.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.1f",
                )
                dpg.add_input_float(
                    tag="pref_reconnect_max",
                    label="Espera máxima de reconexión (s)",
                    width=140,
                    min_value=1.0,
                    max_value=3600.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.0f",
                )
                dpg.add_combo(
                    tag="pref_host_key_policy",
                    label="Claves de servidor desconocidas",
                    items=["auto", "reject"],
                    width=160,
                )
            with dpg.collapsing_header(label="Comandos"):
                dpg.add_input_float(
                    tag="pref_command_timeout",
                    label="Timeout por comando (s)",
                    width=140,
                    min_value=1.0,
                    max_value=3600.0,
                    min_clamped=True,
                    max_clamped=True,
                    format="%.0f",
                )
                dpg.add_input_int(
                    tag="pref_parallel",
                    label="Servidores en paralelo",
                    width=140,
                    min_value=1,
                    max_value=64,
                    min_clamped=True,
                    max_clamped=True,
                )
                dpg.add_checkbox(tag="pref_stop_on_failure", label="Excluir servidor si falla el comando")
            with dpg.collapsing_header(label="Interfaz", default_open=True):
                dpg.add_combo(
                    tag="pref_theme",
                    label="Tema",
                    items=[theme_module.DARK, theme_module.LIGHT],
                    width=160,
                )
                dpg.add_input_int(
                    tag="pref_font_size",
                    label="Tamaño de fuente",
                    width=140,
                    min_value=10,
                    max_value=28,
                    min_clamped=True,
                    max_clamped=True,
                )
                dpg.add_input_int(
                    tag="pref_scrollback",
                    label="Líneas de historial por shell",
                    width=160,
                    min_value=200,
                    max_value=20000,
                    min_clamped=True,
                    max_clamped=True,
                )
                dpg.add_input_int(
                    tag="pref_render_lines",
                    label="Líneas visibles por shell",
                    width=160,
                    min_value=50,
                    max_value=2000,
                    min_clamped=True,
                    max_clamped=True,
                )
                dpg.add_input_int(
                    tag="pref_log_lines",
                    label="Líneas del registro",
                    width=160,
                    min_value=200,
                    max_value=50000,
                    min_clamped=True,
                    max_clamped=True,
                )
            dpg.add_text(
                "El tamaño de fuente se aplica al reiniciar; el resto, al guardar.",
                color=_TEXT_DIM,
                wrap=600,
            )
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Guardar", callback=self._on_save, width=130)
                dpg.add_button(label="Valores por defecto", callback=self._on_defaults, width=180)
                dpg.add_button(
                    label="Cerrar",
                    callback=lambda *_: dpg.configure_item("win_prefs", show=False),
                    width=120,
                )
            dpg.add_text("", tag="pref_status", color=_OK_COLOR)

    # --- datos ---

    def open(self) -> None:
        self._load_values(self.app.settings)
        dpg.set_value("pref_status", "")
        self.app.show_window("win_prefs")

    def _load_values(self, settings: dict) -> None:
        scanner = settings["scanner"]
        ssh = settings["ssh"]
        broadcast = settings["broadcast"]
        ui = settings["ui"]
        dpg.set_value("pref_ports", scanner["ports"])
        dpg.set_value("pref_concurrency", int(scanner["concurrency"]))
        dpg.set_value("pref_scan_timeout", float(scanner["connect_timeout"]))
        dpg.set_value("pref_connect_timeout", float(ssh["connect_timeout"]))
        dpg.set_value("pref_keepalive", int(ssh["keepalive"]))
        dpg.set_value("pref_auto_reconnect", bool(ssh["auto_reconnect"]))
        dpg.set_value("pref_reconnect_base", float(ssh["reconnect_base_delay"]))
        dpg.set_value("pref_reconnect_max", float(ssh["reconnect_max_delay"]))
        dpg.set_value("pref_host_key_policy", str(ssh["host_key_policy"]))
        dpg.set_value("pref_command_timeout", float(broadcast["timeout"]))
        dpg.set_value("pref_parallel", int(broadcast["concurrency"]))
        dpg.set_value("pref_stop_on_failure", bool(broadcast["stop_on_failure"]))
        dpg.set_value("pref_theme", str(ui["theme"]))
        dpg.set_value("pref_font_size", int(ui["font_size"]))
        dpg.set_value("pref_scrollback", int(ui["max_scrollback"]))
        dpg.set_value("pref_render_lines", int(ui["shell_render_lines"]))
        dpg.set_value("pref_log_lines", int(ui["max_log_lines"]))

    # --- acciones ---

    def _on_save(self, *_args) -> None:
        try:
            ports = dpg.get_value("pref_ports").strip()
            if not ports:
                raise ValueError("puertos vacíos")
            settings = self.app.settings
            settings["scanner"].update(
                {
                    "ports": ports,
                    "concurrency": int(dpg.get_value("pref_concurrency")),
                    "connect_timeout": float(dpg.get_value("pref_scan_timeout")),
                }
            )
            settings["ssh"].update(
                {
                    "connect_timeout": float(dpg.get_value("pref_connect_timeout")),
                    "keepalive": int(dpg.get_value("pref_keepalive")),
                    "auto_reconnect": bool(dpg.get_value("pref_auto_reconnect")),
                    "reconnect_base_delay": float(dpg.get_value("pref_reconnect_base")),
                    "reconnect_max_delay": float(dpg.get_value("pref_reconnect_max")),
                    "host_key_policy": str(dpg.get_value("pref_host_key_policy")),
                }
            )
            settings["broadcast"].update(
                {
                    "timeout": float(dpg.get_value("pref_command_timeout")),
                    "concurrency": int(dpg.get_value("pref_parallel")),
                    "stop_on_failure": bool(dpg.get_value("pref_stop_on_failure")),
                }
            )
            settings["ui"].update(
                {
                    "theme": str(dpg.get_value("pref_theme")),
                    "font_size": int(dpg.get_value("pref_font_size")),
                    "max_scrollback": int(dpg.get_value("pref_scrollback")),
                    "shell_render_lines": int(dpg.get_value("pref_render_lines")),
                    "max_log_lines": int(dpg.get_value("pref_log_lines")),
                }
            )
        except (TypeError, ValueError) as exc:
            self.app.log.error(f"Preferencias: valor no válido ({exc})")
            dpg.set_value("pref_status", "Hay valores no válidos")
            return

        self.app.log_panel.set_max_lines(int(settings["ui"]["max_log_lines"]))
        self.app.shell_panel.apply_limits(
            int(settings["ui"]["max_scrollback"]),
            int(settings["ui"]["shell_render_lines"]),
        )
        self.app.set_theme(str(settings["ui"]["theme"]))
        self.app.log.ok("Preferencias guardadas")
        dpg.set_value("pref_status", "Guardado. El tamaño de fuente se aplica al reiniciar.")

    def _on_defaults(self, *_args) -> None:
        self._load_values(copy.deepcopy(config.DEFAULT_SETTINGS))
        dpg.set_value("pref_status", "Valores por defecto cargados; pulsa Guardar para aplicarlos.")
