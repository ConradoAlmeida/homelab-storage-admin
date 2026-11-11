"""Cliente mínimo do Credenciais para o login do Storage Admin."""

from __future__ import annotations

from urllib.parse import quote

import requests
from django.conf import settings


def sessao(username: str, app: str) -> dict:
    base = settings.CREDENTIALS_URL
    token = settings.CREDENTIALS_API_TOKEN
    if not base or not token:
        return {"ok": True, "ativo": True, "autorizado": True}
    try:
        resposta = requests.post(
            base + "/api/sessao",
            json={"username": username, "app": app},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        resposta.raise_for_status()
        return resposta.json()
    except (requests.RequestException, ValueError):
        return {"ok": False, "ativo": False, "autorizado": False, "motivo": "fora"}


def painel_base() -> str:
    """URL do Credenciais aberta no navegador (não o hostname interno do Compose)."""
    base = (getattr(settings, "CREDENTIALS_BROWSER_URL", None) or "").strip().rstrip("/")
    if base:
        return base
    interno = (settings.CREDENTIALS_URL or "").strip().rstrip("/")
    if not interno or "moya-credenciais" in interno:
        return ""
    return interno


def urls_usuario(username: str) -> dict[str, str]:
    """Atalhos para os fluxos de identidade bloqueados neste painel no moya."""
    base = painel_base()
    if not base:
        return {}
    enc = quote(username, safe="")
    return {
        "senha": f"{base}/usuarios/senha/?username={enc}",
        "grupos": f"{base}/usuarios/grupos/?username={enc}",
        "conta": f"{base}/usuarios/?username={enc}",
    }


def consultar(username: str, password: str) -> dict:
    base = settings.CREDENTIALS_URL
    token = settings.CREDENTIALS_API_TOKEN
    if not base or not token:
        return {"ok": False, "motivo": "sem_config"}
    try:
        resposta = requests.post(
            base + "/api/verificar",
            json={"username": username, "password": password},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        resposta.raise_for_status()
        return resposta.json()
    except (requests.RequestException, ValueError):
        return {"ok": False, "motivo": "fora"}
