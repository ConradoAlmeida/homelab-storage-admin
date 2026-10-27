"""Bases pequenas para views autenticadas.

As operações privilegiadas continuam explícitas em get()/post(); estas classes
só concentram login e o ciclo de vida padrão do Django.
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
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
