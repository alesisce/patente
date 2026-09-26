"""Temas visuales de Patente: oscuro (por defecto) y claro."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

DARK = "oscuro"
LIGHT = "claro"

_DARK_COLORS = {
    "mvThemeCol_WindowBg": (22, 24, 29),
    "mvThemeCol_ChildBg": (27, 30, 37),
    "mvThemeCol_PopupBg": (30, 33, 40),
    "mvThemeCol_Border": (52, 58, 70),
    "mvThemeCol_FrameBg": (37, 41, 50),
    "mvThemeCol_FrameBgHovered": (48, 54, 66),
    "mvThemeCol_FrameBgActive": (56, 63, 77),
    "mvThemeCol_TitleBg": (26, 29, 35),
    "mvThemeCol_TitleBgActive": (34, 38, 46),
    "mvThemeCol_MenuBarBg": (26, 29, 35),
    "mvThemeCol_Header": (41, 71, 107),
    "mvThemeCol_HeaderHovered": (52, 88, 130),
    "mvThemeCol_HeaderActive": (60, 101, 148),
    "mvThemeCol_Button": (44, 76, 114),
    "mvThemeCol_ButtonHovered": (56, 96, 142),
    "mvThemeCol_ButtonActive": (36, 63, 95),
    "mvThemeCol_Tab": (34, 38, 46),
    "mvThemeCol_TabHovered": (56, 96, 142),
    "mvThemeCol_TabSelected": (44, 76, 114),
    "mvThemeCol_TabActive": (44, 76, 114),
    "mvThemeCol_TabUnfocused": (28, 31, 38),
    "mvThemeCol_TabUnfocusedActive": (38, 42, 51),
    "mvThemeCol_Separator": (52, 58, 70),
    "mvThemeCol_ScrollbarBg": (24, 26, 31),
    "mvThemeCol_ScrollbarGrab": (60, 66, 78),
    "mvThemeCol_TableHeaderBg": (32, 36, 44),
    "mvThemeCol_TableBorderStrong": (52, 58, 70),
    "mvThemeCol_TableBorderLight": (38, 42, 51),
    "mvThemeCol_TableRowBg": (0, 0, 0, 0),
    "mvThemeCol_TableRowBgAlt": (255, 255, 255, 10),
    "mvThemeCol_Text": (222, 224, 228),
    "mvThemeCol_CheckMark": (110, 170, 240),
}

_LIGHT_COLORS = {
    "mvThemeCol_WindowBg": (243, 244, 247),
    "mvThemeCol_ChildBg": (250, 250, 252),
    "mvThemeCol_PopupBg": (255, 255, 255),
    "mvThemeCol_Border": (206, 209, 215),
    "mvThemeCol_FrameBg": (255, 255, 255),
    "mvThemeCol_FrameBgHovered": (237, 240, 245),
    "mvThemeCol_FrameBgActive": (226, 231, 238),
    "mvThemeCol_TitleBg": (232, 235, 240),
    "mvThemeCol_TitleBgActive": (218, 223, 231),
    "mvThemeCol_MenuBarBg": (236, 238, 243),
    "mvThemeCol_Header": (205, 224, 246),
    "mvThemeCol_HeaderHovered": (188, 213, 242),
    "mvThemeCol_HeaderActive": (170, 202, 238),
    "mvThemeCol_Button": (221, 228, 238),
    "mvThemeCol_ButtonHovered": (206, 217, 232),
    "mvThemeCol_ButtonActive": (189, 204, 224),
    "mvThemeCol_Tab": (228, 231, 237),
    "mvThemeCol_TabHovered": (205, 224, 246),
    "mvThemeCol_TabSelected": (240, 242, 246),
    "mvThemeCol_TabActive": (240, 242, 246),
    "mvThemeCol_TabUnfocused": (232, 235, 240),
    "mvThemeCol_TabUnfocusedActive": (240, 242, 246),
    "mvThemeCol_Separator": (206, 209, 215),
    "mvThemeCol_ScrollbarBg": (238, 240, 244),
    "mvThemeCol_ScrollbarGrab": (200, 205, 213),
    "mvThemeCol_TableHeaderBg": (232, 235, 240),
    "mvThemeCol_TableBorderStrong": (206, 209, 215),
    "mvThemeCol_TableBorderLight": (224, 227, 232),
    "mvThemeCol_TableRowBg": (0, 0, 0, 0),
    "mvThemeCol_TableRowBgAlt": (0, 0, 0, 12),
    "mvThemeCol_Text": (38, 41, 47),
    "mvThemeCol_CheckMark": (45, 105, 190),
}

_STYLES = {
    "mvStyleVar_WindowRounding": (6,),
    "mvStyleVar_ChildRounding": (5,),
    "mvStyleVar_FrameRounding": (4,),
    "mvStyleVar_PopupRounding": (5,),
    "mvStyleVar_TabRounding": (4,),
    "mvStyleVar_ScrollbarRounding": (8,),
    "mvStyleVar_WindowPadding": (10, 10),
    "mvStyleVar_FramePadding": (8, 5),
    "mvStyleVar_ItemSpacing": (8, 6),
}


def build(name: str = DARK):
    """Crea el tema indicado y devuelve su etiqueta para bind_theme."""
    colors = _LIGHT_COLORS if str(name).lower() == LIGHT else _DARK_COLORS
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            for key, value in colors.items():
                const = getattr(dpg, key, None)
                if const is not None:
                    dpg.add_theme_color(const, value)
            for key, values in _STYLES.items():
                const = getattr(dpg, key, None)
                if const is not None:
                    dpg.add_theme_style(const, *values)
    return theme
