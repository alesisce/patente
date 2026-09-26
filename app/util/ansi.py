"""Parser ANSI básico y búfer de terminal para las shells interactivas.

Soporta: texto, salto de línea, retorno de carro (barras de progreso),
retroceso, tabuladores y las secuencias CSI más habituales (colores SGR,
borrado de línea/panalla, movimiento horizontal). No pretende ser un
emulador completo de terminal: las aplicaciones de pantalla completa
(vi, top) no se renderizan correctamente.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_FG = (222, 224, 228)

_BASE_COLORS = [
    (0, 0, 0),
    (205, 49, 49),
    (13, 188, 121),
    (229, 229, 16),
    (36, 114, 200),
    (188, 63, 188),
    (17, 168, 205),
    (229, 229, 229),
]
_BRIGHT_COLORS = [
    (102, 102, 102),
    (241, 76, 76),
    (35, 209, 139),
    (245, 245, 67),
    (59, 142, 234),
    (214, 112, 214),
    (41, 184, 219),
    (255, 255, 255),
]


def color_256(index: int) -> tuple[int, int, int]:
    """Color de la paleta xterm de 256 colores."""
    if index < 0:
        return DEFAULT_FG
    if index < 8:
        return _BASE_COLORS[index]
    if index < 16:
        return _BRIGHT_COLORS[index - 8]
    if index < 232:
        value = index - 16
        steps = (0, 95, 135, 175, 215, 255)
        return (steps[value // 36], steps[(value % 36) // 6], steps[value % 6])
    level = min(255, 8 + (index - 232) * 10)
    return (level, level, level)


@dataclass
class Cell:
    char: str
    fg: tuple[int, int, int] = DEFAULT_FG


@dataclass
class Segment:
    text: str
    fg: tuple[int, int, int]


class AnsiTerminal:
    """Búfer de líneas con un cursor de escritura por línea."""

    def __init__(self, max_lines: int = 2000) -> None:
        self.max_lines = max_lines
        self.lines: list[list[Cell]] = [[]]
        self.cursor = 0
        self.dirty = True
        self._fg = DEFAULT_FG
        self._bg: tuple[int, int, int] | None = None
        self._bold = False
        self._reverse = False
        self._state = "text"
        self._params = ""
        self._saved_cursor = 0

    # --- API pública ---

    def feed(self, text: str) -> None:
        for char in text:
            self._feed_char(char)
        self.dirty = True

    def clear(self) -> None:
        self.lines = [[]]
        self.cursor = 0
        self.dirty = True

    def text(self) -> str:
        return "\n".join("".join(cell.char for cell in line).rstrip() for line in self.lines)

    def visible_lines(self, limit: int) -> list[list[Cell]]:
        if limit > 0:
            return self.lines[-limit:]
        return list(self.lines)

    @staticmethod
    def segments(cells: list[Cell]) -> list[Segment]:
        """Agrupa celdas consecutivas con el mismo color (recortando el final)."""
        segments: list[Segment] = []
        for cell in cells:
            if segments and segments[-1].fg == cell.fg:
                segments[-1].text += cell.char
            else:
                segments.append(Segment(cell.char, cell.fg))
        while segments and not segments[-1].text.strip():
            segments.pop()
        if segments:
            segments[-1].text = segments[-1].text.rstrip()
        return segments

    # --- búfer ---

    def _put(self, char: str) -> None:
        line = self.lines[-1]
        while len(line) < self.cursor:
            line.append(Cell(" "))
        cell = Cell(char, self._effective_fg())
        if self.cursor < len(line):
            line[self.cursor] = cell
        else:
            line.append(cell)
        self.cursor += 1

    def _effective_fg(self) -> tuple[int, int, int]:
        fg = self._fg
        if self._bold and fg in _BASE_COLORS:
            fg = _BRIGHT_COLORS[_BASE_COLORS.index(fg)]
        if self._reverse:
            fg = self._bg or (10, 12, 16)
        return fg

    def _trim(self) -> None:
        excess = len(self.lines) - self.max_lines
        if excess > 0:
            del self.lines[:excess]

    # --- parseo ---

    def _feed_char(self, char: str) -> None:
        state = self._state
        if state == "text":
            if char == "\x1b":
                self._state = "esc"
            elif char == "\n":
                self.lines.append([])
                self.cursor = 0
                self._trim()
            elif char == "\r":
                self.cursor = 0
            elif char == "\b":
                self.cursor = max(0, self.cursor - 1)
            elif char == "\t":
                target = (self.cursor // 8 + 1) * 8
                while self.cursor < target:
                    self._put(" ")
            elif char == "\x07":
                pass
            elif char >= " ":
                self._put(char)
        elif state == "esc":
            if char == "[":
                self._state = "csi"
                self._params = ""
            elif char == "]":
                self._state = "osc"
            elif char in "()":
                self._state = "esc_one"
            else:
                self._state = "text"
        elif state == "esc_one":
            self._state = "text"
        elif state == "osc":
            if char == "\x07":
                self._state = "text"
            elif char == "\x1b":
                self._state = "osc_esc"
        elif state == "osc_esc":
            self._state = "text" if char == "\\" else "osc"
        elif state == "csi":
            if char in "0123456789;:?<>":
                self._params += char
            else:
                self._handle_csi(char)
                self._state = "text"

    def _handle_csi(self, final: str) -> None:
        params = self._params.lstrip("?<>")
        if params:
            numbers = [int(part) if part.isdigit() else 0 for part in params.replace(":", ";").split(";")]
        else:
            numbers = []

        if final == "m":
            self._handle_sgr(numbers or [0])
        elif final == "K":
            mode = numbers[0] if numbers else 0
            line = self.lines[-1]
            if mode == 2:
                line.clear()
                self.cursor = 0
            elif mode == 1:
                for index in range(min(self.cursor, len(line))):
                    line[index] = Cell(" ")
            else:
                del line[self.cursor :]
        elif final == "J":
            mode = numbers[0] if numbers else 0
            if mode == 2:
                self.lines = [[]]
                self.cursor = 0
            else:
                del self.lines[-1][self.cursor :]
        elif final in ("H", "f"):
            self.cursor = 0
        elif final == "C":
            self.cursor += numbers[0] if numbers and numbers[0] else 1
        elif final == "D":
            step = numbers[0] if numbers and numbers[0] else 1
            self.cursor = max(0, self.cursor - step)
        elif final == "X":
            count = numbers[0] if numbers and numbers[0] else 1
            line = self.lines[-1]
            for index in range(self.cursor, min(len(line), self.cursor + count)):
                line[index] = Cell(" ")
        elif final == "s":
            self._saved_cursor = self.cursor
        elif final == "u":
            self.cursor = self._saved_cursor
        # A, B, E, F, G y el resto se ignoran

    def _handle_sgr(self, codes: list[int]) -> None:
        index = 0
        while index < len(codes):
            code = codes[index]
            if code == 0:
                self._fg = DEFAULT_FG
                self._bg = None
                self._bold = False
                self._reverse = False
            elif code == 1:
                self._bold = True
            elif code == 22:
                self._bold = False
            elif code == 7:
                self._reverse = True
            elif code == 27:
                self._reverse = False
            elif 30 <= code <= 37:
                self._fg = _BASE_COLORS[code - 30]
            elif code == 39:
                self._fg = DEFAULT_FG
            elif 40 <= code <= 47:
                self._bg = _BASE_COLORS[code - 40]
            elif code == 49:
                self._bg = None
            elif 90 <= code <= 97:
                self._fg = _BRIGHT_COLORS[code - 90]
            elif 100 <= code <= 107:
                self._bg = _BRIGHT_COLORS[code - 100]
            elif code in (38, 48):
                is_fg = code == 38
                color: tuple[int, int, int] | None = None
                if index + 1 < len(codes) and codes[index + 1] == 5 and index + 2 < len(codes):
                    color = color_256(codes[index + 2])
                    index += 2
                elif index + 1 < len(codes) and codes[index + 1] == 2 and index + 4 < len(codes):
                    color = (codes[index + 2], codes[index + 3], codes[index + 4])
                    index += 4
                if color is not None:
                    if is_fg:
                        self._fg = color
                    else:
                        self._bg = color
            index += 1
