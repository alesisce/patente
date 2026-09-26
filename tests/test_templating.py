"""Pruebas de sustitución de variables en comandos."""

from __future__ import annotations

from app.util.templating import render_template


def test_render_all_variables() -> None:
    rendered = render_template(
        "ping {host} -p {port} ({user}/{group})",
        host="10.0.0.1",
        port=2222,
        user="ana",
        group="lab",
    )
    assert rendered == "ping 10.0.0.1 -p 2222 (ana/lab)"


def test_unknown_placeholders_untouched() -> None:
    assert render_template("echo {nope} {host}", host="h", port=22) == "echo {nope} h"


def test_empty_user_and_group() -> None:
    assert render_template("{user}:{group}", host="h", port=22) == ":"
