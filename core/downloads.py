"""Downloads de torrent para as pastas de mídia do Jellyfin."""

from __future__ import annotations

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from .agent import AgentError, agent
from .forms import TorrentAddForm
from .models import AuditLog
from .view_base import AgentPostView, AgentTemplateView, AgentView


class ExigeJellyfinMixin:
    """A página só existe no host em que o container do Jellyfin está instalado."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        from core.context_processors import capacidades_do_host

        if not capacidades_do_host().get("jellyfin"):
            messages.error(request, "O Jellyfin não está instalado neste servidor.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


def _visao():
    return agent.torrent_overview()


def _auditar(request, action, target):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        target=target,
        ip=request.META.get("REMOTE_ADDR"),
    )


class TorrentsView(ExigeJellyfinMixin, AgentTemplateView):
    template_name = "torrents.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"overview": None, "error": None, "form": None})
        try:
            overview = _visao()
        except AgentError as exc:
            context["error"] = str(exc)
            return context
        context["overview"] = overview
        libraries = overview.get("libraries") if isinstance(overview, dict) else []
        client = overview.get("client") if isinstance(overview, dict) else {}
        if (
            isinstance(client, dict)
            and client.get("available")
            and isinstance(libraries, list)
            and libraries
        ):
            context["form"] = TorrentAddForm(libraries=libraries)
        return context


class TorrentStatusView(ExigeJellyfinMixin, AgentView):
    def get(self, request):
        try:
            overview = _visao()
        except AgentError as exc:
            return JsonResponse({"error": str(exc)}, status=503)
        return JsonResponse(
            {
                "active": bool(overview.get("active")),
                "torrents": overview.get("torrents") or [],
            }
        )


class TorrentAddView(ExigeJellyfinMixin, AgentView):
    def post(self, request):
        try:
            overview = _visao()
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("torrents")
        form = TorrentAddForm(request.POST, libraries=overview.get("libraries"))
        if not form.is_valid():
            return render(
                request,
                "torrents.html",
                {"overview": overview, "error": None, "form": form},
            )
        data = form.cleaned_data
        try:
            resultado = agent.torrent_add(data["magnet"], data["library"])
        except AgentError as exc:
            form.add_error(None, str(exc))
            return render(
                request,
                "torrents.html",
                {"overview": overview, "error": None, "form": form},
            )
        _auditar(request, "torrent.add", resultado.get("library") or data["library"])
        messages.success(
            request,
            f"Torrent adicionado em {resultado.get('library') or 'a pasta escolhida'}.",
        )
        return redirect("torrents")


class TorrentActionView(ExigeJellyfinMixin, AgentPostView):
    def post(self, request):
        torrent_hash = request.POST.get("hash", "")
        action = request.POST.get("action", "")
        try:
            agent.torrent_action(torrent_hash, action)
        except AgentError as exc:
            messages.error(request, str(exc))
        else:
            _auditar(request, f"torrent.{action}", torrent_hash)
            if action == "delete_files":
                messages.success(request, "Torrent removido e arquivos apagados.")
            elif action == "delete":
                messages.success(request, "Torrent removido da fila. Os arquivos permanecem.")
            elif action == "pause":
                messages.success(request, "Download pausado.")
            elif action == "resume":
                messages.success(request, "Download retomado.")
        return redirect("torrents")
