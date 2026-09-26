"""Análisis de objetivos de red: CIDR, rangos, listas y puertos."""

from __future__ import annotations

import ipaddress
import re

MAX_HOSTS = 65536
MAX_TARGETS = 200000

_TOKEN_SPLIT = re.compile(r"[\s,;]+")
_HOSTNAME_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?")


def parse_ports(text: str) -> list[int]:
    """Convierte '22, 80-82' en [22, 80, 81, 82]."""
    ports: list[int] = []
    seen: set[int] = set()
    for token in _TOKEN_SPLIT.split(text.strip()):
        if not token:
            continue
        try:
            if "-" in token:
                left, right = token.split("-", 1)
                start, end = int(left), int(right)
                if start > end:
                    start, end = end, start
                if end - start > 65535:
                    raise ValueError
                values: range | list[int] = range(start, end + 1)
            else:
                values = [int(token)]
        except ValueError:
            raise ValueError(f"Puerto no válido: '{token}'") from None
        for port in values:
            if not 1 <= port <= 65535:
                raise ValueError(f"Puerto fuera de rango: {port}")
            if port not in seen:
                seen.add(port)
                ports.append(port)
    if not ports:
        raise ValueError("No se indicó ningún puerto")
    return ports


def parse_targets(text: str) -> tuple[list[str], list[str]]:
    """Convierte el texto de objetivos en una lista de hosts y otra de avisos.

    Acepta IPs, nombres, CIDR (10.0.0.0/24), rangos cortos (10.0.0.10-20) y
    rangos completos (10.0.0.10-10.0.0.20), separados por espacios, comas,
    punto y coma o saltos de línea.
    """
    hosts: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()

    def add(host: str) -> None:
        host = host.strip().lower()
        if host and host not in seen:
            seen.add(host)
            hosts.append(host)

    for token in _TOKEN_SPLIT.split(text.strip()):
        if not token:
            continue
        try:
            if "/" in token:
                network = ipaddress.ip_network(token, strict=False)
                for address in network.hosts():
                    add(str(address))
            elif "-" in token:
                left, _, right = token.partition("-")
                start = ipaddress.ip_address(left)
                if "." in right or ":" in right:
                    end = ipaddress.ip_address(right)
                elif start.version == 4:
                    prefix = ".".join(left.split(".")[:3])
                    end = ipaddress.ip_address(f"{prefix}.{int(right)}")
                else:
                    end = ipaddress.ip_address(int(start) + int(right))
                if start.version != end.version:
                    raise ValueError("el rango mezcla IPv4 e IPv6")
                if int(end) < int(start):
                    start, end = end, start
                count = int(end) - int(start) + 1
                if count > MAX_HOSTS:
                    errors.append(f"'{token}': el rango es demasiado grande ({count} hosts)")
                else:
                    for value in range(int(start), int(end) + 1):
                        add(str(ipaddress.ip_address(value)))
            else:
                try:
                    add(str(ipaddress.ip_address(token)))
                except ValueError:
                    if re.fullmatch(r"[\d.]+", token):
                        errors.append(f"'{token}': la dirección IP no es válida")
                    elif _HOSTNAME_RE.fullmatch(token):
                        add(token)
                    else:
                        errors.append(f"'{token}': no es una IP, red ni nombre válido")
        except ValueError as exc:
            errors.append(f"'{token}': {exc}")
        if len(hosts) > MAX_HOSTS:
            errors.append(f"Demasiados hosts: se limita el escaneo a {MAX_HOSTS}")
            del hosts[MAX_HOSTS:]
            break

    return hosts, errors
