from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .agent import AgentError, agent
from .forms import GroupsForm, PasswordForm, ShareCreateForm, UserCreateForm
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


def _volume_for(path, volumes):
    matches = [vol for vol in volumes if path == vol["mount"] or path.startswith(vol["mount"].rstrip("/") + "/")]
    if not matches:
        return None
    return max(matches, key=lambda vol: len(vol["mount"]))


@login_required
def dashboard(request):
    context = {"agent_error": None, "volumes": [], "shares": [], "snapshots": []}
    try:
        data = agent.df()
        context["volumes"] = data.get("volumes", [])
        shares = agent.list_shares(include_size=True)
        snapshots = agent.snapshot_usage()
        snap_by_path = {item.get("path"): item for item in snapshots}
        for share in shares:
            snap = snap_by_path.get(share.get("path") or "")
            share["snapshot_count"] = snap.get("count") if snap else None
            vol = _volume_for(share.get("path") or "", context["volumes"])
            total = share.get("size_total")
            share["volume_percent"] = (
                round(total / vol["total"] * 100, 1) if vol and vol.get("total") and total else None
            )
        context["shares"] = shares
        context["snapshots"] = snapshots
    except AgentError as exc:
        context["agent_error"] = str(exc)
    return render(request, "dashboard.html", context)


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
        context["shares"] = agent.list_shares(include_size=True)
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
        context["shares"] = agent.snapshot_usage()
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
