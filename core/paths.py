"""Caminhos de share aceitos pelo portal e pelo agente."""

import os

from django.conf import settings


def prefixos_de_share() -> tuple[str, ...]:
    """Prefixos de share. O disco do Jellyfin entra quando está montado."""
    prefixes = list(settings.ALLOWED_PATH_PREFIXES)
    root = (settings.JELLYFIN_ROOT or "").rstrip("/")
    extra = f"{root}/" if root else ""
    if extra and extra not in prefixes and os.path.ismount(root):
        prefixes.append(extra)
    return tuple(prefixes)
