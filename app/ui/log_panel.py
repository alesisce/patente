"""Panel de registro de la aplicación."""

from __future__ import annotations

import itertools

import dearpygui.dearpygui as dpg

from ..events import LogEvent

_LEVEL_RANK = {"info": 0, "ok": 1, "warn": 2, "error": 3}
_LEVEL_COLORS = {
    "info": (140, 145, 155),
    "ok": (45, 170, 110),
    "warn": (200, 150, 40),
    "error": (220, 80, 80),
}
_TEXT_DIM = (120, 126, 136)
_FILTERS = ["Todo", "Aviso y error", "Solo errores"]
_FILTER_MIN = {_FILTERS[0]: 0, _FILTERS[1]: 2, _FILTERS[2]: 3}


class LogPanel:
    """Vista del registro con colores por nivel y filtro por gravedad."""

    def __init__(self, app) -> None:
        self.app = app
        self._counter = itertools.count(1)
        self._tags: list[str] = []
        self._max_lines = int(app.settings.get("ui", {}).get("max_log_lines", 2000))
        self._min_rank = 0

    def build(self) -> None:
        with dpg.group(horizontal=True):
            dpg.add_button(label="Limpiar", callback=self._clear, width=100)
            dpg.add_text("Nivel:", color=_TEXT_DIM)
            dpg.add_combo(
                tag="log_filter",
                items=_FILTERS,
                default_value=_FILTERS[0],
                width=170,
                callback=self._on_filter,
            )
            dpg.add_text("(el filtro se aplica a los mensajes nuevos)", color=_TEXT_DIM)
            dpg.add_spacer(width=16)
            dpg.add_text(f"Archivo: {self.app.log.path}", color=_TEXT_DIM)
        dpg.add_child_window(tag="log_child", border=True, height=-1, horizontal_scrollbar=True)

    def set_max_lines(self, value: int) -> None:
        self._max_lines = max(100, int(value))
        self._trim()

    def handle_event(self, event) -> None:
        if isinstance(event, LogEvent):
            self._append(event)

    def _on_filter(self, *_args) -> None:
        self._min_rank = _FILTER_MIN.get(dpg.get_value("log_filter"), 0)

    def _append(self, event: LogEvent) -> None:
        if _LEVEL_RANK.get(event.level, 0) < self._min_rank:
            return
        if not dpg.does_item_exist("log_child"):
            return
        tag = f"log_line_{next(self._counter)}"
        dpg.add_text(
            event.message,
            color=_LEVEL_COLORS.get(event.level, _LEVEL_COLORS["info"]),
            parent="log_child",
            tag=tag,
        )
        self._tags.append(tag)
        self._trim()
        dpg.set_y_scroll("log_child", -1)

    def _trim(self) -> None:
        while len(self._tags) > self._max_lines:
            tag = self._tags.pop(0)
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

    def _clear(self, *_args) -> None:
        for tag in self._tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._tags.clear()
