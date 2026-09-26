"""Pruebas del análisis de objetivos y puertos."""

from __future__ import annotations

import pytest

from app.util.net import parse_ports, parse_targets


def test_cidr() -> None:
    hosts, errors = parse_targets("192.168.1.0/30")
    assert hosts == ["192.168.1.1", "192.168.1.2"]
    assert errors == []


def test_short_range() -> None:
    hosts, _ = parse_targets("10.0.0.10-12")
    assert hosts == ["10.0.0.10", "10.0.0.11", "10.0.0.12"]


def test_full_range() -> None:
    hosts, _ = parse_targets("10.0.0.250-10.0.0.252")
    assert hosts == ["10.0.0.250", "10.0.0.251", "10.0.0.252"]


def test_single_ip_and_hostname_with_dedupe() -> None:
    hosts, errors = parse_targets("Servidor.Local, servidor.local, 10.0.0.1")
    assert hosts == ["servidor.local", "10.0.0.1"]
    assert errors == []


def test_invalid_token() -> None:
    hosts, errors = parse_targets("999.1.1.1")
    assert hosts == []
    assert errors


def test_mixed_separators() -> None:
    hosts, _ = parse_targets("10.0.0.1;10.0.0.2\n10.0.0.3,10.0.0.4")
    assert hosts == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"]


def test_empty() -> None:
    assert parse_targets("") == ([], [])


def test_ports_list_and_range() -> None:
    assert parse_ports("22, 80-82") == [22, 80, 81, 82]
    assert parse_ports("2222,22,2222") == [2222, 22]


@pytest.mark.parametrize("text", ["0", "abc", "70000", ""])
def test_ports_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_ports(text)
