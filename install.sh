#!/usr/bin/env bash
# Instala las dependencias de Patente en un entorno virtual local (.venv)
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 no encontrado. Instálalo (p. ej. 'sudo apt install python3 python3-venv')." >&2
    exit 1
fi

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo
echo "Instalación completada. Ejecuta: ./run.sh"
