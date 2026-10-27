from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render

from core.agent import AgentError, agent
from core.hostinfo import volume_for
from core.view_base import AgentPostView, AgentTemplateView


class StorageIndexView(AgentTemplateView):
    template_name = "storage/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "overview": None,
                "error": None,
                "volumes": [],
                "totals": None,
            }
        )
        try:
            context["overview"] = agent.storage_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        try:
            context["volumes"] = agent.df().get("volumes", [])
        except AgentError:
            context["volumes"] = []
        volumes = context["volumes"]
        if volumes:
            context["totals"] = {
                "total": sum(int(v.get("total") or 0) for v in volumes),
                "used": sum(int(v.get("used") or 0) for v in volumes),
                "free": sum(int(v.get("free") or 0) for v in volumes),
            }
        if context["overview"]:
            for disk in context["overview"].get("disks", []):
                volume = None
                for mount in disk.get("mounts") or []:
                    volume = volume_for(mount, volumes)
                    if volume:
                        break
                disk["volume"] = volume
        return context


class StorageRefreshView(AgentPostView):
    def post(self, request):
        try:
            agent.refresh_storage()
        except AgentError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Métricas de storage/SMART atualizadas.")
        return redirect("storage_index")


class StorageSmartView(AgentPostView):
    def post(self, request):
        device = (request.POST.get("device") or "").strip()
        context = {"device": device, "result": None, "error": None}
        if not device:
            context["error"] = "Dispositivo nao informado"
        else:
            try:
                context["result"] = agent.storage_smart(device)
            except AgentError as exc:
                context["error"] = str(exc)
        return render(request, "storage/smart.html", context)


class StorageSmartTestView(AgentPostView):
    def post(self, request):
        device = (request.POST.get("device") or "").strip()
        kind = (request.POST.get("kind") or "short").strip()
        try:
            result = agent.storage_smart_test(device, kind)
        except AgentError as exc:
            messages.error(request, str(exc))
        else:
            label = "curto" if result.get("kind") == "short" else "longo"
            messages.success(
                request,
                f"Teste SMART {label} iniciado em {result.get('device')}. "
                "O resultado aparece no proximo 'Ler SMART' quando terminar.",
            )
        return redirect("storage_index")
