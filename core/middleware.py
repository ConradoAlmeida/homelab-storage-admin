"""Bloqueia só a gestão de identidade que o Credenciais assumiu.

As rotas continuam existindo para o Pi e para qualquer host que não ative a
flag. O bloqueio é por host, via CREDENTIALS_MANAGE_USERS.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponseNotFound
from django.shortcuts import redirect

from .credenciais import sessao

BLOQUEADOS = (
    "/usuarios/novo/",
    "/usuarios/senha/",
    "/usuarios/toggle/",
    "/usuarios/excluir/",
)
EXATO = {"/usuarios/grupos/"}


class GestaoUsuariosCredenciaisMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.CREDENTIALS_MANAGE_USERS:
            caminho = request.path
            if caminho in EXATO or any(
                caminho == prefixo or caminho.startswith(prefixo)
                for prefixo in BLOQUEADOS
            ):
                return HttpResponseNotFound(
                    "Gestão de identidade centralizada no Credenciais."
                )
        return self.get_response(request)


class SessaoCredenciaisMiddleware:
    """Revalida a sessão a cada request quando o Credenciais está ativo."""

    PUBLICOS = ("/login/", "/logout/", "/static/", "/health/", "/favicon.ico")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.CREDENTIALS_URL or not settings.CREDENTIALS_API_TOKEN:
            return self.get_response(request)
        if not request.user.is_authenticated:
            return self.get_response(request)
        if request.user.is_superuser or request.user.username == "admin":
            return self.get_response(request)
        if request.path.startswith(self.PUBLICOS):
            return self.get_response(request)
        dados = sessao(request.user.username, settings.CREDENTIALS_APP)
        if not dados.get("ok") or not dados.get("autorizado"):
            logout(request)
            messages.error(request, "Seu acesso ao Storage Admin foi encerrado.")
            return redirect("login")
        return self.get_response(request)
