"""Contexto comum: nome do site e capacidades do host.

As capacidades são consultadas no agente e mantidas por alguns segundos para
não abrir um socket em cada página. Se o agente estiver indisponível, o
template recebe um dicionário vazio e simplesmente esconde os recursos
opcionais; as views continuam tratando o erro.
"""
from __future__ import annotations

import time

from django.conf import settings

from .agent import AgentError, agent

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
        "capabilities": _cached_caps,
        "storage_root": settings.STORAGE_ROOT,
        "snapshot_root": settings.SNAPSHOT_ROOT,
        "backup_root": settings.BACKUP_ROOT,
    }
