"""Cliente mínimo do Credenciais para o login do Storage Admin."""

from __future__ import annotations

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
