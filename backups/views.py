import mimetypes
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.agent import AgentError, agent
from core.models import AuditLog

from .defaults import DEFAULT_EXCLUDES_TEXT

LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
WEEKDAYS = [
    (0, "Segunda"),
    (1, "Terça"),
    (2, "Quarta"),
    (3, "Quinta"),
    (4, "Sexta"),
    (5, "Sábado"),
    (6, "Domingo"),
]


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
def snapshots(request):
    context = {"snapshots": [], "errors": [], "error": None}
    try:
        data = agent.backup_snapshots()
        context["snapshots"] = data.get("snapshots", [])
        context["errors"] = data.get("errors", [])
    except AgentError as exc:
        context["error"] = str(exc)
    return render(request, "backups/snapshots.html", context)


def _snapshot_browse_url(snapshot_id: str, disk_uuid: str, path: str) -> str:
    base = reverse("backup_snapshot_browse", args=[snapshot_id])
    return f"{base}?{urlencode({'disk_uuid': disk_uuid, 'path': path})}"


def _snapshot_breadcrumbs(path: str) -> list[dict]:
    current = ""
    crumbs = []
    for part in PurePosixPath(path).parts:
        if part == "/":
            current = "/"
            name = "/"
        else:
            current = f"{current.rstrip('/')}/{part}"
            name = part
        crumbs.append({"name": name, "path": current})
    return crumbs


def _safe_download_path(relative: str) -> Path | None:
    if not relative:
        return None
    root = Path(settings.DATA_DIR).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


@login_required
def snapshot_browse(request, snapshot_id):
    disk_uuid = (request.GET.get("disk_uuid") or "").strip()
    path = (request.GET.get("path") or "/mnt/nas").strip()
    context = {
        "snapshot_id": snapshot_id,
        "disk_uuid": disk_uuid,
        "path": path,
        "parent": str(PurePosixPath(path).parent),
        "breadcrumbs": _snapshot_breadcrumbs(path),
        "entries": [],
        "error": None,
    }
    try:
        data = agent.backup_ls(disk_uuid, snapshot_id, path)
    except AgentError as exc:
        context["error"] = str(exc)
    else:
        context.update(
            {
                "snapshot_id": data.get("snapshot_id") or snapshot_id,
                "path": data.get("path") or path,
                "parent": data.get("parent") or context["parent"],
                "breadcrumbs": _snapshot_breadcrumbs(data.get("path") or path),
                "entries": data.get("entries") or [],
            }
        )
    return render(request, "backups/snapshot_browse.html", context)


@login_required
def snapshot_download(request, snapshot_id):
    disk_uuid = (request.GET.get("disk_uuid") or "").strip()
    path = (request.GET.get("path") or "").strip()
    try:
        result = agent.backup_download(disk_uuid, snapshot_id, path)
    except AgentError as exc:
        messages.error(request, f"Não foi possível baixar o arquivo: {exc}")
        return redirect(_snapshot_browse_url(snapshot_id, disk_uuid, path))

    target = _safe_download_path(result.get("relative") or "")
    if target is None or not target.is_file():
        messages.error(request, "Arquivo de download não encontrado no app.")
        return redirect(_snapshot_browse_url(snapshot_id, disk_uuid, path))

    filename = result.get("filename") or target.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    AuditLog.objects.create(
        actor=request.user,
        action="backup_snapshot_download",
        target=snapshot_id,
        detail=path,
        ip=request.META.get("REMOTE_ADDR"),
    )
    response = FileResponse(
        open(target, "rb"),
        as_attachment=True,
        filename=filename,
        content_type=content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


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


@login_required
def credentials(request):
    context = {
        "overview": None,
        "disks": [],
        "result": None,
        "error": None,
        "selected_uuid": (request.GET.get("uuid") or "").strip(),
    }
    try:
        overview = agent.backup_overview()
    except AgentError as exc:
        context["error"] = str(exc)
        return render(request, "backups/credentials.html", context)
    context["overview"] = overview
    context["disks"] = [
        disk for disk in overview.get("disks", []) if disk.get("configured")
    ]

    if request.method == "POST":
        uuid = (request.POST.get("uuid") or "").strip()
        password = request.POST.get("password") or ""
        context["selected_uuid"] = uuid
        if not uuid:
            context["error"] = "Selecione um disco configurado."
        elif not request.user.check_password(password):
            context["error"] = "Senha do app incorreta."
        else:
            try:
                result = agent.backup_secret(uuid)
            except AgentError as exc:
                context["error"] = str(exc)
            else:
                context["result"] = result
                AuditLog.objects.create(
                    actor=request.user,
                    action="backup_secret_reveal",
                    target=uuid,
                    detail=f"label={result.get('label', '')}",
                    ip=request.META.get("REMOTE_ADDR"),
                )
    return render(request, "backups/credentials.html", context)


def _default_job_form(overview: dict) -> dict:
    disks = [disk for disk in overview.get("disks", []) if disk.get("configured")]
    return {
        "name": "",
        "disk_uuid": disks[0]["uuid"] if disks else "",
        "sources": [],
        "excludes_text": DEFAULT_EXCLUDES_TEXT,
        "frequency": "daily",
        "time": "03:30",
        "weekday": 0,
        "monthday": 1,
        "retention": {"daily": 7, "weekly": 4, "monthly": 6},
        "enabled": True,
    }


def _job_form_from_job(job: dict) -> dict:
    schedule = job.get("schedule") or {}
    retention = job.get("retention") or {}
    return {
        "name": job.get("name", ""),
        "disk_uuid": job.get("disk_uuid", ""),
        "sources": job.get("sources") or [],
        "excludes_text": "\n".join(job.get("excludes") or []),
        "frequency": schedule.get("frequency", "daily"),
        "time": schedule.get("time", "03:30"),
        "weekday": schedule.get("weekday", 0) or 0,
        "monthday": schedule.get("monthday", 1) or 1,
        "retention": {
            "daily": retention.get("daily", 0),
            "weekly": retention.get("weekly", 0),
            "monthly": retention.get("monthly", 0),
        },
        "enabled": bool(job.get("enabled", True)),
    }


@login_required
def job_form(request, name=None):
    try:
        overview = agent.backup_overview()
    except AgentError as exc:
        return render(
            request,
            "backups/job_form.html",
            {"overview": None, "error": str(exc), "disks": [], "shares": []},
        )
    try:
        shares = agent.list_shares(include_size=False)
    except AgentError as exc:
        shares = []
        shares_error = str(exc)
    else:
        shares_error = None
    disks = [disk for disk in overview.get("disks", []) if disk.get("configured")]

    job = None
    if name:
        job = next(
            (item for item in overview.get("jobs", []) if item.get("name") == name),
            None,
        )
        if job is None:
            messages.error(request, f"Job não encontrado: {name}")
            return redirect("backup_index")

    error = None
    if request.method == "POST":
        form_name = (
            job.get("name") if job else request.POST.get("name") or ""
        ).strip().lower()
        form = {
            "name": form_name,
            "disk_uuid": request.POST.get("disk_uuid") or "",
            "sources": request.POST.getlist("sources"),
            "excludes_text": request.POST.get("excludes") or "",
            "frequency": request.POST.get("frequency") or "daily",
            "time": request.POST.get("time") or "03:30",
            "weekday": request.POST.get("weekday") or "0",
            "monthday": request.POST.get("monthday") or "1",
            "retention": {
                "daily": request.POST.get("keep_daily") or "0",
                "weekly": request.POST.get("keep_weekly") or "0",
                "monthly": request.POST.get("keep_monthly") or "0",
            },
            "enabled": request.POST.get("enabled") == "on",
        }
        if not form_name:
            error = "Informe o nome do job."
        elif job is None and any(
            item.get("name") == form_name for item in overview.get("jobs", [])
        ):
            error = "Já existe um job com esse nome; edite o existente."
        elif not disks:
            error = "Nenhum disco de backup configurado. Prepare um disco primeiro."
        elif not shares:
            error = "Nenhum share encontrado."
        else:
            payload = {
                "name": form_name,
                "disk_uuid": form["disk_uuid"],
                "sources": form["sources"],
                "excludes": form["excludes_text"].splitlines(),
                "schedule": {
                    "frequency": form["frequency"],
                    "time": form["time"],
                    "weekday": form["weekday"],
                    "monthday": form["monthday"],
                },
                "retention": form["retention"],
                "enabled": form["enabled"],
            }
            try:
                result = agent.backup_job_save(payload)
            except AgentError as exc:
                error = str(exc)
            else:
                AuditLog.objects.create(
                    actor=request.user,
                    action="backup_job_save",
                    target=result.get("name", form_name),
                    detail=(
                        f"enabled={result.get('enabled')} "
                        f"schedule={result.get('schedule', {}).get('label', '')}"
                    ),
                    ip=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, f"Job {form_name} salvo.")
                return redirect("backup_index")
    else:
        form = _job_form_from_job(job) if job else _default_job_form(overview)

    return render(
        request,
        "backups/job_form.html",
        {
            "overview": overview,
            "disks": disks,
            "shares": shares,
            "shares_error": shares_error,
            "weekdays": WEEKDAYS,
            "job": job,
            "form": form,
            "error": error,
            "default_excludes_text": DEFAULT_EXCLUDES_TEXT,
        },
    )


@login_required
@require_POST
def job_run(request, name):
    try:
        agent.backup_job_run(name)
    except AgentError as exc:
        messages.error(request, str(exc))
    else:
        AuditLog.objects.create(
            actor=request.user,
            action="backup_job_run",
            target=name,
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(
            request, f"Backup {name} iniciado. Atualize a página para ver o status."
        )
    return redirect("backup_index")


@login_required
@require_POST
def job_toggle(request, name):
    enabled = request.POST.get("enabled") == "1"
    try:
        agent.backup_job_toggle(name, enabled)
    except AgentError as exc:
        messages.error(request, str(exc))
    else:
        AuditLog.objects.create(
            actor=request.user,
            action="backup_job_toggle",
            target=name,
            detail=f"enabled={enabled}",
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(
            request, f"Job {name} {'ativado' if enabled else 'desativado'}."
        )
    return redirect("backup_index")


@login_required
@require_POST
def job_delete(request, name):
    try:
        agent.backup_job_delete(name)
    except AgentError as exc:
        messages.error(request, str(exc))
    else:
        AuditLog.objects.create(
            actor=request.user,
            action="backup_job_delete",
            target=name,
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(
            request, f"Job {name} excluído. O repositório restic foi mantido."
        )
    return redirect("backup_index")


@login_required
def cold_index(request):
    context = {"overview": None, "error": None}
    try:
        context["overview"] = agent.cold_overview()
    except AgentError as exc:
        context["error"] = str(exc)
    return render(request, "backups/cold_index.html", context)


@login_required
def cold_prepare(request):
    try:
        overview = agent.cold_overview()
    except AgentError as exc:
        return render(
            request,
            "backups/cold_prepare.html",
            {"overview": None, "selected": None, "error": str(exc)},
        )
    device = (request.POST.get("device") or request.GET.get("device") or "").strip()
    if not device:
        return redirect("cold_index")
    selected = next(
        (disk for disk in overview.get("disks", []) if disk["path"] == device), None
    )
    if selected is None:
        return render(
            request,
            "backups/cold_prepare.html",
            {"overview": overview, "selected": None, "error": f"Drive não encontrado: {device}"},
        )

    error = None
    if request.method == "POST":
        password = request.POST.get("password") or ""
        label = (request.POST.get("label") or "").strip().lower()
        confirmation = request.POST.get("confirmation") or ""
        acknowledge = request.POST.get("acknowledge") == "1"
        if not selected["candidate"]:
            error = f"Drive indisponível: {selected['reason']}"
        elif not request.user.check_password(password):
            error = "Senha do app incorreta."
        elif selected["extra_confirmation"] and not acknowledge:
            error = "Marque a confirmação extra para drive não vazio/configurado."
        elif not LABEL_RE.match(label):
            error = "Label inválida: use 1–16 caracteres a-z, 0-9, _ ou -."
        else:
            try:
                result = agent.cold_prepare(
                    device,
                    label,
                    confirmation,
                    allow_existing=selected["extra_confirmation"],
                )
            except AgentError as exc:
                error = str(exc)
            else:
                AuditLog.objects.create(
                    actor=request.user,
                    action="cold_prepare",
                    target=device,
                    detail=f"label={label}",
                    ip=request.META.get("REMOTE_ADDR"),
                )
                return render(
                    request,
                    "backups/cold_result.html",
                    {"result": result, "disk": selected, "action": "prepared"},
                )

    if (
        request.method == "GET"
        and selected["extra_confirmation"]
        and selected["candidate"]
        and request.GET.get("confirm") != "1"
    ):
        return render(
            request,
            "backups/cold_warning.html",
            {"overview": overview, "selected": selected},
        )

    return render(
        request,
        "backups/cold_prepare.html",
        {
            "overview": overview,
            "selected": selected,
            "error": error,
            "default_label": _default_label(selected),
        },
    )


@login_required
@require_POST
def cold_copy(request):
    try:
        result = agent.cold_copy()
    except AgentError as exc:
        messages.error(request, str(exc))
    else:
        AuditLog.objects.create(
            actor=request.user,
            action="cold_copy",
            target=result.get("device", ""),
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(
            request,
            "Cópia fria iniciada em segundo plano. Atualize a página para acompanhar o status.",
        )
    return redirect("cold_index")


@login_required
@require_POST
def cold_eject(request):
    try:
        agent.cold_eject()
    except AgentError as exc:
        messages.error(request, str(exc))
    else:
        AuditLog.objects.create(
            actor=request.user,
            action="cold_eject",
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Drive frio ejetado. Pode desconectar com segurança.")
    return redirect("cold_index")
