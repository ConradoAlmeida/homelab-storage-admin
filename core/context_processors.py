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


def _asset_version() -> str:
    """Versao de cache das folhas de estilo, derivada do mtime dos arquivos."""
    css_dir = settings.BASE_DIR / "static" / "css"
    try:
        stamps = [path.stat().st_mtime_ns for path in css_dir.glob("*.css")]
    except OSError:
        stamps = []
    return str(max(stamps)) if stamps else "1"


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
    caps = capacidades_do_host()
    return {
        "tarefa": bruto,
        "site_name": settings.SITE_NAME,
        "product_name": settings.SITE_NAME,
        "static_version": _asset_version(),
        "brand_homelab": visual["homelab"],
        "brand_logo": visual["logo"],
        "brand_login_logo": visual["login_logo"],
        "brand_alt": visual["alt"],
        "capabilities": caps,
        "credenciais_gerencia_usuarios": settings.CREDENTIALS_MANAGE_USERS,
        "system_manage": settings.SYSTEM_MANAGE,
        "terminal_menu": bool(
            getattr(settings, "TERMINAL_ENABLE", False)
            and caps.get("terminal_enable")
        ),
        "django_admin_manage": bool(
            getattr(settings, "DJANGO_ADMIN_MANAGE", False)
            and caps.get("django_admin")
        ),
        "login_pelo_credenciais": bool(
            settings.CREDENTIALS_URL and settings.CREDENTIALS_API_TOKEN
        ),
        "storage_root": settings.STORAGE_ROOT,
        "snapshot_root": settings.SNAPSHOT_ROOT,
        "backup_root": settings.BACKUP_ROOT,
        "services": load_services(settings.SERVICES_FILE),
    }
