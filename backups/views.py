import re

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.agent import AgentError, agent

LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")


def _default_label(disk: dict) -> str:
    raw = (disk.get("label") or "backup").strip().lower()
    raw = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-_")
    if not raw or not raw[0].isalnum():
        raw = f"backup-{raw}".strip("-")
    return raw[:16] or "backup"


@login_required
def index(request):
    context = {"overview": None, "error": None}
    try:
        context["overview"] = agent.backup_overview()
    except AgentError as exc:
        context["error"] = str(exc)
    return render(request, "backups/index.html", context)


@login_required
def disk_wizard(request):
    try:
        overview = agent.backup_overview()
    except AgentError as exc:
        return render(
            request,
            "backups/disk_wizard.html",
            {"overview": None, "selected": None, "error": str(exc)},
        )

    device = (request.POST.get("device") or request.GET.get("device") or "").strip()
    if not device:
        return redirect("backup_index")
    selected = next(
        (disk for disk in overview.get("disks", []) if disk["path"] == device), None
    )
    error = None
    if selected is None:
        error = f"Disco nao encontrado: {device}"
        return render(
            request,
            "backups/disk_wizard.html",
            {"overview": overview, "selected": None, "error": error},
        )

    if request.method == "POST":
        password = request.POST.get("password") or ""
        label = (request.POST.get("label") or "").strip().lower()
        confirmation = request.POST.get("confirmation") or ""
        acknowledge = request.POST.get("acknowledge") == "1"

        if not selected["candidate"]:
            error = f"Disco indisponivel: {selected['reason']}"
        elif not request.user.check_password(password):
            error = "Senha do app incorreta."
        elif selected["extra_confirmation"] and not acknowledge:
            error = "Marque a confirmação extra para disco não vazio/configurado."
        elif not LABEL_RE.match(label):
            error = "Label inválida: use 1–16 caracteres a-z, 0-9, _ ou -."
        else:
            try:
                result = agent.backup_disk_setup(
                    device,
                    label,
                    confirmation,
                    allow_existing=selected["extra_confirmation"],
                )
            except AgentError as exc:
                error = str(exc)
            else:
                return render(
                    request,
                    "backups/disk_result.html",
                    {"result": result, "disk": selected},
                )

    if (
        request.method == "GET"
        and selected["extra_confirmation"]
        and selected["candidate"]
        and request.GET.get("confirm") != "1"
    ):
        return render(
            request,
            "backups/disk_warning.html",
            {"overview": overview, "selected": selected},
        )

    return render(
        request,
        "backups/disk_wizard.html",
        {
            "overview": overview,
            "selected": selected,
            "error": error,
            "default_label": _default_label(selected),
        },
    )
