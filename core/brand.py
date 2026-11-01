"""Marca visual por host.

O homelab usa a casa com servidores. O moya, onde o Credenciais gerencia as
pessoas, mantém o wordmark Moya. A escolha segue CREDENTIALS_MANAGE_USERS,
a mesma flag que já separa os dois ambientes.
"""

from __future__ import annotations

from django.conf import settings


def marca() -> dict:
    if settings.CREDENTIALS_MANAGE_USERS:
        return {
            "homelab": False,
            "logo": "images/moya_wordmark_official.svg",
            "login_logo": "images/moya_wordmark_official.svg",
            "alt": "Moya",
            "favicon": "images/favicon.ico",
        }
    return {
        "homelab": True,
        "logo": "images/conrado/mark.png",
        "login_logo": "images/conrado/lockup.png",
        "alt": "Conrado Homelab",
        "favicon": "images/conrado/favicon.ico",
    }
