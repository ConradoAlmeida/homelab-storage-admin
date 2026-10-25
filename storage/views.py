from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.agent import AgentError, agent


@login_required
def index(request):
    context = {"overview": None, "error": None}
    try:
        context["overview"] = agent.storage_overview()
    except AgentError as exc:
        context["error"] = str(exc)
    return render(request, "storage/index.html", context)


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
