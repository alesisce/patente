# Instala las dependencias de Patente en un entorno virtual local (.venv)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python no encontrado. Instala Python 3.10 o superior desde https://www.python.org/"
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "Instalación completada. Ejecuta: .\run.bat" -ForegroundColor Green
