"""Utilidades del texto de comandos: análisis de líneas y detección de riesgo."""

from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(?:-[^\s]+\s+)*-[^\s]*[rf]", re.IGNORECASE), "borrado recursivo o forzado (rm -rf)"),
    (re.compile(r"\bmkfs(\.\w+)?\b", re.IGNORECASE), "formateo de sistema de archivos (mkfs)"),
    (re.compile(r"\bdd\b[^|;&]*\bof=/dev/", re.IGNORECASE), "escritura directa a un dispositivo (dd)"),
    (re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.IGNORECASE), "apagado o reinicio del equipo"),
    (re.compile(r":\s*\(\s*\)\s*\{.*\}\s*;\s*:", re.IGNORECASE), "bomba fork"),
    (re.compile(r"\bchmod\s+-R\s+777\s+/(\s|$)", re.IGNORECASE), "permisos 777 sobre la raíz"),
    (re.compile(r"\bchown\s+-R\s+\S+\s+/(\s|$)", re.IGNORECASE), "cambio de propietario de todo el sistema"),
    (re.compile(r">\s*/dev/(sd[a-z]|nvme\d|hd[a-z]|vd[a-z])", re.IGNORECASE), "redirección a un disco completo"),
    (re.compile(r"\bkill(all)?\s+-9\s+1\b", re.IGNORECASE), "matar el proceso init"),
    (re.compile(r"\buserdel\b[^|;&]*-r\b", re.IGNORECASE), "borrar un usuario y su directorio"),
    (re.compile(r"\bmv\s+[^|;&]*\s+/\s*$", re.IGNORECASE), "mover archivos sobre la raíz"),
]


def parse_commands(text: str) -> list[str]:
    """Convierte el texto en una lista de comandos (una línea por comando).

    Se ignoran las líneas vacías y las que empiezan por '#'.
    """
    commands: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        commands.append(line)
    return commands


def find_dangerous(commands: list[str]) -> list[str]:
    """Devuelve la lista de motivos de riesgo encontrados (sin repetir)."""
    reasons: list[str] = []
    for command in commands:
        for pattern, reason in _RULES:
            if reason not in reasons and pattern.search(command):
                reasons.append(reason)
    return reasons
