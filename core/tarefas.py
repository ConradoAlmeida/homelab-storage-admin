"""Disparo de trabalho longo: audita o gatilho e devolve a página com a tarefa."""

from __future__ import annotations

from django.contrib import messages

from .models import AuditLog


def disparo(request, resultado, *, action: str, target: str, detail: str = "") -> str:
    task = ""
    if isinstance(resultado, dict):
        bruto = resultado.get("task")
        if isinstance(bruto, str):
            task = bruto
    AuditLog.objects.create(
        actor=request.user,
        action=action,
        target=target,
        detail=detail or (f"tarefa={task}" if task else ""),
        ip=request.META.get("REMOTE_ADDR"),
    )
    messages.success(
        request, "Trabalho iniciado. Esta página acompanha o andamento."
    )
    return task


def com_tarefa(url: str, task: str) -> str:
    if not task:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}tarefa={task}"
