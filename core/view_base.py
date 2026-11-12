"""Bases pequenas para views autenticadas.

As operações privilegiadas continuam explícitas em get()/post(); estas classes
só concentram login e o ciclo de vida padrão do Django.
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views import View
from django.views.generic import FormView, TemplateView


class AgentView(LoginRequiredMixin, View):
    """View autenticada para fluxos explícitos."""


class AgentPostView(LoginRequiredMixin, View):
    """View autenticada que aceita apenas POST."""

    http_method_names = ["post"]


class AgentFormView(LoginRequiredMixin, FormView):
    """FormView autenticada."""


class AgentTemplateView(LoginRequiredMixin, TemplateView):
    """TemplateView autenticada."""


class SuperuserRequiredMixin(LoginRequiredMixin):
    """Alem do login, exige superuser local (break-glass)."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class SuperuserPostView(SuperuserRequiredMixin, View):
    """View de superuser que aceita apenas POST."""

    http_method_names = ["post"]


class SuperuserTemplateView(SuperuserRequiredMixin, TemplateView):
    """TemplateView de superuser."""
