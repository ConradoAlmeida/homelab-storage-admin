"""Contexto comum: nome do site e capacidades do host.

As capacidades são consultadas no agente e mantidas por alguns segundos para
não abrir um socket em cada página. Se o agente estiver indisponível, o
template recebe um dicionário vazio e simplesmente esconde os recursos
opcionais; as views continuam tratando o erro.
"""
from __future__ import annotations

import re
import time

from django.conf import settings

from .agent import AgentError, agent
from .brand import marca
from .services import load_services

_TAREFA_RE = re.compile(r"^[a-z0-9]+-[a-f0-9]{8}$")
_CACHE_SECONDS = 30
_cached_at = 0.0
_cached_caps: dict | None = None


def capacidades_do_host() -> dict:
    """Capacidades do agente, reutilizadas por alguns segundos."""
    global _cached_at, _cached_caps
    now = time.monotonic()
    if _cached_caps is None or now - _cached_at > _CACHE_SECONDS:
        try:
            _cached_caps = agent.host_capabilities()
        except AgentError:
            _cached_caps = {}
        _cached_at = now
    return _cached_caps


def homelab(request):
    visual = marca()
    bruto = ""
    if request is not None and hasattr(request, "GET"):
        bruto = (request.GET.get("tarefa") or "").strip()
    if not _TAREFA_RE.match(bruto):
        bruto = ""
    return {
        "tarefa": bruto,
        "site_name": settings.SITE_NAME,
        "product_name": settings.SITE_NAME,
        "brand_homelab": visual["homelab"],
        "brand_logo": visual["logo"],
        "brand_login_logo": visual["login_logo"],
        "brand_alt": visual["alt"],
        "capabilities": capacidades_do_host(),
        "credenciais_gerencia_usuarios": settings.CREDENTIALS_MANAGE_USERS,
        "login_pelo_credenciais": bool(
            settings.CREDENTIALS_URL and settings.CREDENTIALS_API_TOKEN
        ),
        "storage_root": settings.STORAGE_ROOT,
        "snapshot_root": settings.SNAPSHOT_ROOT,
        "backup_root": settings.BACKUP_ROOT,
        "services": load_services(settings.SERVICES_FILE),
    }
