"""Marca visual por host.

O homelab usa Conradhub Homelab: CONRADHUB é a marca e HOMELAB a linha
secundária. O moya, onde o Credenciais gerencia as pessoas, mantém o
wordmark Moya. A escolha segue CREDENTIALS_MANAGE_USERS, a mesma flag que
já separa os dois ambientes.
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
        "logo": "images/conradhub/mark.png",
        "login_logo": "images/conradhub/wordmark.png",
        "alt": "Conradhub Homelab",
        "favicon": "images/conradhub/favicon.ico",
    }
