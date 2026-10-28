"""Bloqueia só a gestão de identidade que o Credenciais assumiu.

As rotas continuam existindo para o Pi e para qualquer host que não ative a
flag. O bloqueio é por host, via CREDENTIALS_MANAGE_USERS.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseNotFound

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
