# Patente

Escáner de red y cliente SSH con interfaz gráfica, pensado para administrar
varios servidores a la vez. Construido con [DearPyGui](https://github.com/hoffstadt/DearPyGui)
y [paramiko](https://github.com/paramiko/paramiko).
Compatible con Windows y Linux.

## Estado: fases M1–M5 completas

- **Escáner TCP asíncrono**: acepta IPs, nombres, CIDR (`192.168.1.0/24`),
  rangos cortos (`10.0.0.10-25`) y rangos completos, separados por comas,
  espacios, punto y coma o saltos de línea.
- **Detección de SSH por banner** (sin completar el handshake): identifica el
  software y la versión (`OpenSSH_9.6p1`, `dropbear_...`), con latencia por host.
- **Progreso cancelable** y resultados en vivo, con filtro y columna “Añadir”.
- **Inventario de servidores** con exclusión (columna *Activo*): los servidores
  desactivados no recibirán el envío masivo de las fases siguientes.
  Añadir/eliminar, activar/desactivar por lotes, filtro, notas y grupos.
- **Importar y exportar** en JSON o CSV.
- **Conexión SSH (paramiko)**: la contraseña se pide al conectar y **solo vive
  en memoria**; nunca se escribe en disco. Se puede aplicar la misma credencial
  a todos los seleccionados o pedir una por servidor.
- **Estado por servidor** con colores (Desconectado, Conectando, Conectado,
  Error) y detalle (versión remota o causa del fallo).
- **Reconexión automática** con backoff exponencial y keepalive, si se guardó
  la credencial en memoria; errores de credenciales no se reintentan.
- **Envío masivo de comandos** (ventana *Comandos*): arriba una tabla con los
  servidores conectados (casilla *Enviar* por servidor, botones *Todos* y
  *Ninguno*) y abajo un campo para el comando. Cada servidor recibe el comando
  y el paralelismo es entre servidores; el timeout, el paralelismo y la
  exclusión al fallar están en *Opciones avanzadas*.
- **Abrir shells desde ahí mismo**: botón *shell* en cada fila o *Abrir shell
  en seleccionados*.
- **Variables en comandos**: `{host}`, `{port}`, `{user}` y `{group}` se
  sustituyen por cada servidor, con *Vista previa* para comprobarlo.
- **Resultados por comando**: código de salida, duración, estado y resumen;
  el detalle (salida y errores completos, con copia al portapapeles) se abre
  en su propia ventana.
- **Aviso de comandos peligrosos** (`rm -rf`, `mkfs`, `dd of=/dev/...`, apagado,
  bomba fork...) con confirmación antes de enviar.
- **Historial** de los últimos envíos para reutilizarlos.
- **Shells interactivas**: cada shell se abre en su propia ventana, con
  pty real, tamaño ajustado a la ventana y botones Ctrl+C, Ctrl+D, Ctrl+Z y Tab.
- **Modo "escribir a todas"**: lo que escribes se envía a todas las shells
  abiertas a la vez.
- **Colores ANSI** (16, 256 y truecolor), con soporte de `\r` para barras de
  progreso, retroceso, borrado de línea y de pantalla. Los programas de
  pantalla completa (vi, top) no se renderizan.
- **Transcripción**: limpiar, copiar al portapapeles o guardar a archivo.
- **Tema oscuro y claro**: se cambia desde *Ver → Tema* o desde *Preferencias*.
- **Preferencias** (*Ver → Preferencias*, F5): escáner, conexiones SSH, comandos,
  tema, fuentes, historial y registro, sin editar archivos a mano.
- **Exportar resultados** del escáner y de los comandos a CSV o JSON.
- **Favoritos de comandos**: guarda los comandos que más uses con un nombre.
- **Registro** con niveles, filtro por gravedad (aviso/error) y archivo en disco.
- **Atajos**: F1 Acerca de · F2 Escáner · F3 Comandos · F4 Registro · F5 Preferencias.

Estado: las cinco fases (M1–M5) están completas. No se incluye empaquetado
(Ejecutable); la aplicación se ejecuta desde el entorno virtual.

## Requisitos

- Python 3.10 o superior.
- Linux: bibliotecas gráficas del sistema.
  - Debian/Ubuntu: `sudo apt install libgl1 libxinerama1 libxcursor1 libxi6 libxrandr2`
  - Fedora: `sudo dnf install mesa-libGL libXinerama libXcursor libXi libXrandr`
  - Arch: `sudo pacman -S mesa libxinerama libxcursor libxi libxrandr`

## Instalación

Windows (PowerShell):

```powershell
.\install.ps1
.\run.bat
```

Linux:

```bash
chmod +x install.sh run.sh
./install.sh
./run.sh
```

Instalación manual (cualquier sistema):

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python.exe
python main.py
```

## Uso

- **Interfaz**: `python main.py` (o `run.bat` / `run.sh`).
- **Escaneo sin interfaz**, útil para pruebas:

```bash
python main.py --scan "192.168.1.0/24" --ports 22,2222 --timeout 1.5
```

Flujo típico: abre la ventana *Escáner* desde la barra superior → escribe los
objetivos → *Escanear* → selecciona los resultados SSH → *Añadir seleccionados
al inventario* → marca servidores con *Sel.* y pulsa *Conectar* → abre shells
con *Abrir shell* o lanza comandos desde *Comandos…*.

La ventana principal es el inventario con menú y barra de acciones; el
escáner, los comandos, el registro, las preferencias y cada shell se abren
como ventanas independientes (*Ver* y *Shells*) y *Ver → Organizar en cascada*
las recoloca. Los ajustes se editan en *Ver → Preferencias* (F5).

## Estructura

```
patente/
  main.py                  # punto de entrada y escaneo por consola
  app/
    config.py              # rutas multiplataforma y ajustes
    models.py              # Server, ScanResult
    events.py              # bus de eventos (hilos → interfaz)
    log.py                 # registro a archivo y a la interfaz
    inventory.py           # inventario con persistencia
    snippets.py            # favoritos de comandos
    scanner.py             # escáner asíncrono con banner SSH
    ssh/                   # sesiones paramiko, gestor y envío masivo
    ui/                    # interfaz DearPyGui (ventana, paneles, tema, preferencias)
    util/net.py            # análisis de CIDR, rangos y puertos
    util/commands.py       # análisis de comandos y detección de riesgo
    util/templating.py     # variables {host}, {user}, {port}, {group}
    util/ansi.py           # parser ANSI y búfer de terminal
    util/report.py         # exportación de informes a CSV o JSON
  assets/fonts/            # fuente con glifos latinos
  tests/                   # pruebas con pytest (incluye servidor SSH de prueba)
```

## Pruebas

```bash
python -m pytest            # o .venv/bin/python -m pytest
```

## Datos y registros

La configuración y el inventario se guardan en el directorio de usuario de cada
sistema (por ejemplo `~/.config/patente` y `~/.local/share/patente` en Linux,
`%LOCALAPPDATA%\patente` en Windows). La ruta exacta del archivo de registro
aparece en la ventana *Registro*.
