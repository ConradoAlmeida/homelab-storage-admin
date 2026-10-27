from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .agent import AgentError, agent
from .forms import (
    GroupCreateForm,
    GroupsForm,
    PasswordForm,
    ShareCreateForm,
    UserCreateForm,
)
from .hostinfo import disk_role, volume_for
from .models import AuditLog


def _audit(request, action, target="", detail=""):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        target=target,
        detail=detail,
        ip=request.META.get("REMOTE_ADDR"),
    )


def _error(request, exc):
    messages.error(request, str(exc))


@login_required
def dashboard(request):
    context = {
        "agent_error": None,
        "volumes": [],
        "shares": [],
        "snapshots": [],
        "storage": None,
        "backups": None,
        "backup_jobs": [],
        "snapshots_summary": {},
        "raid_status": "—",
    }
    try:
        data = agent.df()
        context["volumes"] = data.get("volumes", [])
        context["shares"] = agent.list_shares(include_size=False)
        context["snapshots"] = agent.snapshot_usage(include_size=False)
        storage = agent.storage_overview()
        backups = agent.backup_overview()
    except AgentError as exc:
        context["agent_error"] = str(exc)
        return render(request, "dashboard.html", context)

    volumes = context["volumes"]
    for disk in storage.get("disks", []):
        mounts = disk.get("mounts") or []
        volume = None
        for mount in mounts:
            volume = volume_for(mount, volumes)
            if volume:
                break
        disk["volume"] = volume
        disk["role"] = disk_role(
            disk,
            settings.STORAGE_ROOT,
            settings.BACKUP_ROOT,
            settings.JELLYFIN_ROOT,
        )

    backup_disks = backups.get("disks", [])
    backup_jobs = backups.get("jobs", [])
    for job in backup_jobs:
        disk = next(
            (item for item in backup_disks if item.get("uuid") == job.get("disk_uuid")),
            None,
        )
        mount = (disk or {}).get("mountpoint")
        job["volume"] = volume_for(mount, volumes) if mount else None
        job["source_count"] = len(job.get("sources") or [])

    snapshots = context["snapshots"]
    snap_by_name = {item.get("share"): item for item in snapshots}
    for share in context["shares"]:
        snap = snap_by_name.get(share.get("name"))
        share["snapshot_enabled"] = bool(snap and snap.get("enabled"))
        share["snapshot_keep"] = snap.get("keep") if snap else None
        share["snapshot_count"] = int(snap.get("count") or 0) if snap else 0
    total_count = sum(int(item.get("count") or 0) for item in snapshots)
    total_size = sum(int(item.get("size") or 0) for item in snapshots)
    latest = None
    for item in snapshots:
        for snap in item.get("snapshots") or []:
            if latest is None or snap.get("name", "") > latest.get("name", ""):
                latest = snap
    context["snapshots_summary"] = {
        "policies": len(snapshots),
        "enabled": sum(1 for item in snapshots if item.get("enabled")),
        "count": total_count,
        "size": total_size,
        "latest": latest,
    }

    mdstat = (storage.get("raid") or {}).get("mdstat", "")
    if "[U_]" in mdstat or "[_U]" in mdstat:
        context["raid_status"] = "degradado"
    elif "[UU]" in mdstat:
        context["raid_status"] = "ok"
    context["storage"] = storage
    context["backups"] = backups
    context["backup_jobs"] = backup_jobs
    return render(request, "dashboard.html", context)


@login_required
def network_metrics(request):
    try:
        data = agent.network_metrics()
    except AgentError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    return JsonResponse(data)


@login_required
def share_sizes(request):
    """Tamanhos dos shares carregados depois do render do dashboard."""
    try:
        shares = agent.list_shares(include_size=True)
    except AgentError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    return JsonResponse(
        {
            "shares": [
                {
                    "name": item.get("name"),
                    "size": item.get("size"),
                    "size_snapshots": item.get("size_snapshots"),
                    "size_total": item.get("size_total"),
                }
                for item in shares
            ]
        }
    )


@login_required
def users(request):
    context = {"agent_error": None, "users": []}
    try:
        context["users"] = agent.list_users()
    except AgentError as exc:
        context["agent_error"] = str(exc)
    return render(request, "users.html", context)


@login_required
def user_create(request):
    try:
        group_choices = agent.list_groups()
    except AgentError as exc:
        messages.error(request, str(exc))
        return redirect("users")

    form = UserCreateForm(request.POST or None, group_choices=group_choices)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            agent.create_user(data["username"], data["password"], data["groups"])
            _audit(request, "user.create", data["username"], f"groups={','.join(data['groups'])}")
            messages.success(request, f"Usuario {data['username']} criado.")
            return redirect("users")
        except AgentError as exc:
            _error(request, exc)
    return render(request, "user_form.html", {"form": form})


@login_required
def group_create(request):
    form = GroupCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            result = agent.create_group(data["name"], data.get("gid"))
            _audit(
                request,
                "group.create",
                data["name"],
                f"gid={result.get('gid') or 'auto'}",
            )
            messages.success(request, f"Grupo {data['name']} criado.")
            return redirect("users")
        except AgentError as exc:
            _error(request, exc)
    return render(request, "group_form.html", {"form": form})


@login_required
def user_password(request):
    username = request.GET.get("username") or request.POST.get("username", "")
    form = PasswordForm(request.POST or None, initial={"username": username})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            agent.set_password(data["username"], data["password"])
            _audit(request, "user.password", data["username"])
            messages.success(request, f"Senha de {data['username']} atualizada.")
            return redirect("users")
        except AgentError as exc:
            _error(request, exc)
    username = request.GET.get("username", "")
    return render(request, "user_password.html", {"form": form, "username": username})


@login_required
def user_groups(request):
    username = request.GET.get("username") or request.POST.get("username", "")
    try:
        group_choices = agent.list_groups()
        users = agent.list_users()
    except AgentError as exc:
        messages.error(request, str(exc))
        return redirect("users")

    current = next((u for u in users if u["username"] == username), None)
    form = GroupsForm(
        request.POST or None,
        group_choices=group_choices,
        initial_groups=current["groups"] if current else [],
        initial={"username": username},
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            agent.set_groups(data["username"], data["groups"])
            _audit(request, "user.groups", data["username"], f"groups={','.join(data['groups'])}")
            messages.success(request, f"Grupos de {data['username']} atualizados.")
            return redirect("users")
        except AgentError as exc:
            _error(request, exc)
    return render(request, "user_groups.html", {"form": form, "username": username})


@login_required
@require_POST
def user_toggle(request):
    username = request.POST.get("username", "")
    enabled = request.POST.get("enabled") == "1"
    try:
        agent.toggle_user(username, enabled)
        _audit(request, "user.enable" if enabled else "user.disable", username)
        messages.success(request, f"Usuario {username} {'habilitado' if enabled else 'desabilitado'}.")
    except AgentError as exc:
        _error(request, exc)
    return redirect("users")


@login_required
def shares(request):
    context = {"agent_error": None, "shares": []}
    try:
        shares = agent.list_shares(include_size=True)
        snap_by_name = {
            item.get("share"): item for item in agent.snapshot_usage()
        }
        for share in shares:
            snap = snap_by_name.get(share.get("name"))
            share["snapshot_enabled"] = bool(snap and snap.get("enabled"))
            share["snapshot_keep"] = snap.get("keep") if snap else None
            share["snapshot_count"] = snap.get("count") if snap else 0
        context["shares"] = shares
    except AgentError as exc:
        context["agent_error"] = str(exc)
    return render(request, "shares.html", context)


@login_required
def share_create(request):
    form = ShareCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            agent.create_share(
                name=data["name"],
                path=data["path"],
                comment=data.get("comment", ""),
                snapshot=data.get("snapshot", False),
                snapshot_keep=data.get("snapshot_keep") or 7,
                private=data.get("private", False),
            )
            _audit(
                request,
                "share.create",
                data["name"],
                f"path={data['path']} snapshot={data.get('snapshot', False)} private={data.get('private', False)}",
            )
            messages.success(request, f"Share {data['name']} criado.")
            return redirect("shares")
        except AgentError as exc:
            _error(request, exc)
    return render(request, "share_form.html", {"form": form})


@login_required
def snapshots(request):
    context = {"agent_error": None, "shares": []}
    try:
        policies = {
            item.get("share"): item for item in agent.snapshot_usage()
        }
        shares = agent.list_shares(include_size=False)
        result = []
        seen = set()
        for share in shares:
            name = share.get("name")
            item = policies.get(name)
            if item is None:
                item = {
                    "share": name,
                    "path": share.get("path"),
                    "enabled": False,
                    "keep": 0,
                    "count": 0,
                    "size": 0,
                    "snapshots": [],
                }
            result.append(item)
            seen.add(name)
        for name, item in policies.items():
            if name not in seen:
                result.append(item)
        context["shares"] = sorted(result, key=lambda item: item.get("share", ""))
        context["summary"] = {
            "total": len(result),
            "enabled": sum(1 for item in result if item.get("enabled")),
            "count": sum(int(item.get("count") or 0) for item in result),
            "size": sum(int(item.get("size") or 0) for item in result),
        }
    except AgentError as exc:
        context["agent_error"] = str(exc)
    return render(request, "snapshots.html", context)


@login_required
@require_POST
def snapshot_create(request):
    share = request.POST.get("share", "")
    try:
        result = agent.snapshot_create(share)
        _audit(request, "snapshot.create", f"{share}/{result.get('name', '')}")
        messages.success(request, f"Snapshot criado para {share}: {result.get('name', '')}")
    except AgentError as exc:
        _error(request, exc)
    return redirect("snapshots")


@login_required
@require_POST
def snapshot_delete(request):
    share = request.POST.get("share", "")
    name = request.POST.get("name", "")
    try:
        agent.snapshot_delete(share, name)
        _audit(request, "snapshot.delete", f"{share}/{name}")
        messages.success(request, f"Snapshot removido: {share}/{name}")
    except AgentError as exc:
        _error(request, exc)
    return redirect("snapshots")
