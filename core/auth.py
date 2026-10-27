"""Login do Storage Admin via Credenciais, com admin local de emergência."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .credenciais import consultar


def _mensagem(motivo: str) -> str:
    if motivo == "trocar_senha":
        return "Troque a senha temporária no Credenciais antes de entrar aqui."
    if motivo == "sem_config":
        return "O Credenciais não está configurado neste Storage Admin."
    if motivo == "fora":
        return "O Credenciais não respondeu."
    return "Usuário ou senha inválidos."


def _destino(request, next_url: str):
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("dashboard")


def login_view(request):
    if request.user.is_authenticated:
        return _destino(request, request.GET.get("next", ""))

    erro = ""
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        nome = (request.POST.get("username") or "").strip()
        senha = request.POST.get("password") or ""

        # Emergência: mantém o admin local funcionando se o Credenciais cair.
        if nome == "admin":
            local = authenticate(request, username=nome, password=senha)
            if local is not None:
                login(request, local)
                return _destino(request, next_url)

        resultado = consultar(nome, senha)
        if resultado.get("ok") and settings.CREDENTIALS_APP in (resultado.get("apps") or []):
            User = get_user_model()
            pessoa, criada = User.objects.get_or_create(username=nome)
            if criada:
                pessoa.set_unusable_password()
            pessoa.is_active = True
            pessoa.save()
            login(
                request,
                pessoa,
                backend="django.contrib.auth.backends.ModelBackend",
            )
            return _destino(request, next_url)

        if resultado.get("ok"):
            erro = "Sua conta não tem acesso ao Storage Admin."
        else:
            erro = _mensagem(resultado.get("motivo"))

    return render(request, "login.html", {"erro": erro, "next": next_url})
