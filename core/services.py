"""Atalhos de serviços configurados por host.

O app não descobre nem sonda serviços. Ele apenas renderiza os atalhos que o
operador escolheu em ``services.ini`` (por exemplo, Jellyfin, Cockpit, Gitea).
"""
from __future__ import annotations

import configparser
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_COLOR = "#38bdf8"


@dataclass(frozen=True)
class Service:
    key: str
    name: str
    description: str
    url: str
    icon: str
    color: str
    order: int


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def load_services(path: str | Path | None) -> list[Service]:
    if not path:
        return []
    config_path = Path(path)
    if not config_path.is_file():
        return []

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(config_path, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        logger.warning("services.ini invalido (%s): %s", config_path, exc)
        return []

    services: list[Service] = []
    for section in parser.sections():
        if section.lower() in {"global", "default"}:
            continue
        url = (parser.get(section, "url", fallback="") or "").strip()
        if not _valid_url(url):
            logger.warning("services.ini: URL invalida em [%s]: %r", section, url)
            continue
        name = (parser.get(section, "name", fallback="") or section).strip() or section
        description = (parser.get(section, "description", fallback="") or "").strip()
        icon = (parser.get(section, "icon", fallback="generic") or "generic").strip()
        color = (parser.get(section, "color", fallback=DEFAULT_COLOR) or "").strip()
        if not COLOR_RE.match(color):
            color = DEFAULT_COLOR
        try:
            order = int(parser.get(section, "order", fallback="100"))
        except ValueError:
            order = 100
        services.append(
            Service(
                key=section,
                name=name,
                description=description,
                url=url,
                icon=icon,
                color=color,
                order=order,
            )
        )
    return sorted(services, key=lambda item: (item.order, item.name.casefold()))
