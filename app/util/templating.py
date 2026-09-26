"""Sustitución de variables en comandos: {host}, {port}, {user}, {group}."""

from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"\{(host|port|user|group)\}")


def render_template(
    text: str,
    *,
    host: str,
    port: int,
    user: str = "",
    group: str = "",
) -> str:
    """Reemplaza las variables conocidas; las desconocidas se dejan intactas."""
    values = {"host": host, "port": str(port), "user": user, "group": group}
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], text)
