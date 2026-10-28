"""Contexto comum: nome do site e capacidades do host.

As capacidades s├úo consultadas no agente e mantidas por alguns segundos para
n├úo abrir um socket em cada p├ígina. Se o agente estiver indispon├¡vel, o
template recebe um dicion├írio vazio e simplesmente esconde os recursos
opcionais; as views continuam tratando o erro.
"""
from __future__ import annotations

import time

from django.conf import settings

from .agent import AgentError, agent
from .services import load_services

_CACHE_SECONDS = 30
_cached_at = 0.0
_cached_caps: dict | None = None


def homelab(request):
    global _cached_at, _cached_caps
    now = time.monotonic()
    if _cached_caps is None or now - _cached_at > _CACHE_SECONDS:
        try:
            _cached_caps = agent.host_capabilities()
        except AgentError:
            _cached_caps = {}
        _cached_at = now
    return {
        "site_name": settings.SITE_NAME,
        "product_name": settings.SITE_NAME,
        "capabilities": _cached_caps,
        "storage_root": settings.STORAGE_ROOT,
        "snapshot_root": settings.SNAPSHOT_ROOT,
        "backup_root": settings.BACKUP_ROOT,
        "services": load_services(settings.SERVICES_FILE),
    }
