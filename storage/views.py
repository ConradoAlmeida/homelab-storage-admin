from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.agent import AgentError, agent
from core.hostinfo import volume_for


@login_required
def index(request):
    context = {
        "overview": None,
        "error": None,
        "volumes": [],
        "totals": None,
    }
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
    return render(request, "storage/index.html", context)


@login_required
@require_POST
def refresh(request):
    try:
        agent.refresh_storage()
        messages.success(request, "Métricas de storage/SMART atualizadas.")
    except AgentError as exc:
        messages.error(request, str(exc))
    return redirect("storage_index")


@login_required
@require_POST
def smart(request):
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


@login_required
@require_POST
def smart_test(request):
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
