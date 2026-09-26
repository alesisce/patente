"""Pruebas del análisis de comandos y la detección de riesgo."""

from __future__ import annotations

from app.util.commands import find_dangerous, parse_commands


def test_parse_commands_ignores_blanks_and_comments() -> None:
    assert parse_commands("uptime\n\n# nota\n  df -h  \n") == ["uptime", "df -h"]


def test_parse_commands_empty() -> None:
    assert parse_commands("\n# solo comentarios\n") == []


def test_dangerous_detected() -> None:
    reasons = find_dangerous(["sudo rm -rf /tmp/x", "reboot"])
    assert any("rm" in reason for reason in reasons)
    assert any("apagado" in reason for reason in reasons)


def test_dangerous_union_without_duplicates() -> None:
    reasons = find_dangerous(["rm -rf /a", "rm -rf /b", "shutdown -h now"])
    assert len(reasons) == 2


def test_more_dangerous_patterns() -> None:
    assert find_dangerous(["mkfs.ext4 /dev/sda1"])
    assert find_dangerous(["dd if=/dev/zero of=/dev/sda bs=1M"])
    assert find_dangerous([":(){ :|:& };:"])
    assert find_dangerous(["kill -9 1"])


def test_safe_commands_pass() -> None:
    assert find_dangerous(["uptime", "df -h", "ls -la", "systemctl status nginx", "kill -9 4242"]) == []
