"""Configuración, rutas multiplataforma y persistencia de Patente."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "patente"
APP_TITLE = "Patente"
APP_VERSION = "0.4.0"

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

DEFAULT_SETTINGS: dict[str, Any] = {
    "scanner": {
        "ports": "22",
        "concurrency": 100,
        "connect_timeout": 2.0,
        "banner_timeout": 2.0,
    },
    "ui": {
        "theme": "oscuro",
        "font_size": 15,
        "max_log_lines": 2000,
        "max_scrollback": 2000,
        "shell_render_lines": 300,
    },
    "ssh": {
        "connect_timeout": 10.0,
        "auth_timeout": 15.0,
        "keepalive": 30,
        "auto_reconnect": True,
        "reconnect_base_delay": 3.0,
        "reconnect_max_delay": 60.0,
        "monitor_interval": 2.0,
        "host_key_policy": "auto",
    },
    "broadcast": {
        "timeout": 30.0,
        "concurrency": 8,
        "stop_on_failure": True,
    },
}


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """Directorio de configuración (~/.config/patente, %LOCALAPPDATA%\\patente)."""
    return _ensure_dir(Path(user_config_dir(APP_NAME)))


def data_dir() -> Path:
    """Directorio de datos (~/.local/share/patente, %LOCALAPPDATA%\\patente)."""
    return _ensure_dir(Path(user_data_dir(APP_NAME)))


def log_dir() -> Path:
    """Directorio de registros."""
    return _ensure_dir(Path(user_log_dir(APP_NAME)))


def settings_path() -> Path:
    return config_dir() / "settings.json"


def servers_path() -> Path:
    return data_dir() / "servers.json"


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return copy.deepcopy(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return copy.deepcopy(DEFAULT_SETTINGS)
    return _deep_merge(copy.deepcopy(DEFAULT_SETTINGS), data)


def save_settings(settings: dict[str, Any]) -> None:
    atomic_write_json(settings_path(), settings)


def atomic_write_json(path: Path, data: Any) -> None:
    """Escribe JSON de forma atómica (archivo temporal + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
