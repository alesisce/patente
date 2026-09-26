"""Pruebas del parser ANSI y del búfer de terminal."""

from __future__ import annotations

from app.util.ansi import DEFAULT_FG, AnsiTerminal, color_256


def _line(terminal: AnsiTerminal, index: int = -1) -> str:
    return "".join(cell.char for cell in terminal.lines[index])


def test_plain_text_and_newline() -> None:
    terminal = AnsiTerminal()
    terminal.feed("hola\nmundo")
    assert terminal.lines[0][0].char == "h"
    assert _line(terminal, 0) == "hola"
    assert _line(terminal, -1) == "mundo"


def test_carriage_return_overwrites() -> None:
    terminal = AnsiTerminal()
    terminal.feed("progreso 10%\rprogreso 90%")
    assert _line(terminal) == "progreso 90%"


def test_backspace() -> None:
    terminal = AnsiTerminal()
    terminal.feed("abc\bX")
    assert _line(terminal) == "abX"


def test_tab_advances_to_next_multiple_of_eight() -> None:
    terminal = AnsiTerminal()
    terminal.feed("a\tb")
    assert terminal.lines[-1][8].char == "b"


def test_sgr_basic_color() -> None:
    terminal = AnsiTerminal()
    terminal.feed("\x1b[31mrojo\x1b[0mnormal")
    segments = AnsiTerminal.segments(terminal.lines[-1])
    assert [segment.text for segment in segments] == ["rojo", "normal"]
    assert segments[0].fg == (205, 49, 49)
    assert segments[1].fg == DEFAULT_FG


def test_sgr_bold_makes_base_colors_bright() -> None:
    terminal = AnsiTerminal()
    terminal.feed("\x1b[1;32mverde")
    segments = AnsiTerminal.segments(terminal.lines[-1])
    assert segments[0].fg == (35, 209, 139)


def test_sgr_256_color_and_truecolor() -> None:
    terminal = AnsiTerminal()
    terminal.feed("\x1b[38;5;196mX\x1b[38;2;10;20;30mY")
    segments = AnsiTerminal.segments(terminal.lines[-1])
    assert segments[0].fg == color_256(196) == (255, 0, 0)
    assert segments[1].fg == (10, 20, 30)


def test_erase_line_and_screen() -> None:
    terminal = AnsiTerminal()
    terminal.feed("basura\x1b[2Kok")
    assert _line(terminal) == "ok"
    terminal.feed("\x1b[2J")
    assert terminal.lines == [[]]


def test_osc_sequences_ignored() -> None:
    terminal = AnsiTerminal()
    terminal.feed("\x1b]0;titulo\x07hola")
    assert _line(terminal) == "hola"


def test_max_lines_trims_old_output() -> None:
    terminal = AnsiTerminal(max_lines=2)
    terminal.feed("uno\ndos\ntres")
    assert terminal.text() == "dos\ntres"


def test_text_strips_trailing_spaces() -> None:
    terminal = AnsiTerminal()
    terminal.feed("hola   \nmundo")
    assert terminal.text() == "hola\nmundo"


def test_clear() -> None:
    terminal = AnsiTerminal()
    terminal.feed("algo")
    terminal.clear()
    assert terminal.lines == [[]]
    assert terminal.text() == ""
