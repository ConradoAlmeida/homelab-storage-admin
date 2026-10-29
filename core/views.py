from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy

from .agent import AgentError, agent
from .forms import (
    GroupCreateForm,
    GroupsForm,
    PasswordForm,
    ShareCreateForm,
    UserCreateForm,
)
from .hostinfo import disk_role, volume_for
from .http import agent_json_error
from .models import AuditLog
from .view_base import AgentFormView, AgentPostView, AgentTemplateView, AgentView


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


class DashboardView(AgentTemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "agent_error": None,
                "volumes": [],
                "shares": [],
                "snapshots": [],
                "storage": None,
                "backups": None,
                "backup_jobs": [],
                "arquivos_jobs": [],
                "arquivos_dir": "",
                "snapshots_summary": {},
                "raid_status": "-",
                "health": None,
            }
        )
        try:
            data = agent.df()
            context["volumes"] = data.get("volumes", [])
            context["shares"] = agent.list_shares(include_size=False)
            context["snapshots"] = agent.snapshot_usage(include_size=False)
            storage = agent.storage_overview()
            backups = agent.backup_overview()
        except AgentError as exc:
            context["agent_error"] = str(exc)
            return context

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
                (
                    item
                    for item in backup_disks
                    if item.get("uuid") == job.get("disk_uuid")
                ),
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
        try:
            arquivos = agent.arquivos_jobs()
        except AgentError:
            pass
        else:
            context["arquivos_jobs"] = arquivos.get("jobs", [])
            context["arquivos_dir"] = arquivos.get("dir", "")
        try:
            context["health"] = agent.health_overview()
        except AgentError:
            pass
        return context


class NetworkView(AgentTemplateView):
    template_name = "network.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"data": None, "error": None})
        try:
            context["data"] = agent.network_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        return context


class NetworkMetricsView(AgentView):
    def get(self, request):
        try:
            data = agent.network_metrics()
        except AgentError as exc:
            return agent_json_error(exc)
        return JsonResponse(data)


class LiveMetricsView(AgentView):
    def get(self, request):
        """Hardware do Pi em tempo real; discos/SMART continuam no cache."""
        try:
            data = agent.live_metrics()
        except AgentError as exc:
            return agent_json_error(exc)
        return JsonResponse(data)


class ShareSizesView(AgentView):
    def get(self, request):
        """Tamanhos dos shares carregados depois do render do dashboard."""
        try:
            shares = agent.list_shares(include_size=True)
        except AgentError as exc:
            return agent_json_error(exc)
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


class UsersView(AgentTemplateView):
    template_name = "users.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"agent_error": None, "users": []})
        context["groups"] = []
        try:
            context["users"] = agent.list_users()
        except AgentError as exc:
            context["agent_error"] = str(exc)
            return context
        try:
            nomes = agent.list_groups()
        except AgentError as exc:
            context["agent_error"] = str(exc)
            return context
        contas = {item["username"] for item in context["users"]}
        context["groups"] = [nome for nome in nomes if nome not in contas]
        return context


class UserCreateView(AgentFormView):
    template_name = "user_form.html"
    form_class = UserCreateForm
    success_url = reverse_lazy("users")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        try:
            self.group_choices = agent.list_groups()
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("users")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["group_choices"] = getattr(self, "group_choices", [])
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            agent.create_user(data["username"], data["password"], data["groups"])
        except AgentError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        _audit(
            self.request,
            "user.create",
            data["username"],
            f"groups={','.join(data['groups'])}",
        )
        messages.success(self.request, f"Usuario {data['username']} criado.")
        return super().form_valid(form)


class GroupCreateView(AgentFormView):
    template_name = "group_form.html"
    form_class = GroupCreateForm
    success_url = reverse_lazy("users")

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            result = agent.create_group(data["name"], data.get("gid"))
        except AgentError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        _audit(
            self.request,
            "group.create",
            data["name"],
            f"gid={result.get('gid') or 'auto'}",
        )
        messages.success(self.request, f"Grupo {data['name']} criado.")
        return super().form_valid(form)


class UserPasswordView(AgentFormView):
    template_name = "user_password.html"
    form_class = PasswordForm
    success_url = reverse_lazy("users")

    def get_initial(self):
        initial = super().get_initial()
        username = self.request.GET.get("username") or self.request.POST.get(
            "username", ""
        )
        initial["username"] = username
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["username"] = (
            self.request.GET.get("username")
            or self.request.POST.get("username", "")
        )
        return context

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            agent.set_password(data["username"], data["password"])
        except AgentError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        _audit(self.request, "user.password", data["username"])
        messages.success(
            self.request, f"Senha de {data['username']} atualizada."
        )
        return super().form_valid(form)


class UserGroupsView(AgentFormView):
    template_name = "user_groups.html"
    form_class = GroupsForm
    success_url = reverse_lazy("users")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        try:
            self.group_choices = agent.list_groups()
            self.users = agent.list_users()
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("users")
        return super().dispatch(request, *args, **kwargs)

    def get_username(self) -> str:
        return (
            self.request.GET.get("username")
            or self.request.POST.get("username", "")
        )

    def get_initial(self):
        initial = super().get_initial()
        username = self.get_username()
        current = next(
            (user for user in getattr(self, "users", []) if user["username"] == username),
            None,
        )
        initial["username"] = username
        initial["groups"] = current["groups"] if current else []
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["group_choices"] = getattr(self, "group_choices", [])
        kwargs["initial_groups"] = self.get_initial().get("groups", [])
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["username"] = self.get_username()
        return context

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            agent.set_groups(data["username"], data["groups"])
        except AgentError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        _audit(
            self.request,
            "user.groups",
            data["username"],
            f"groups={','.join(data['groups'])}",
        )
        messages.success(
            self.request, f"Grupos de {data['username']} atualizados."
        )
        return super().form_valid(form)


class UserToggleView(AgentPostView):
    def post(self, request):
        username = request.POST.get("username", "")
        enabled = request.POST.get("enabled") == "1"
        try:
            agent.toggle_user(username, enabled)
        except AgentError as exc:
            _error(request, exc)
        else:
            _audit(
                request,
                "user.enable" if enabled else "user.disable",
                username,
            )
            messages.success(
                request,
                f"Usuario {username} {'habilitado' if enabled else 'desabilitado'}.",
            )
        return redirect("users")


class UserDeleteView(AgentPostView):
    def post(self, request):
        username = request.POST.get("username", "")
        try:
            agent.delete_user(username)
        except AgentError as exc:
            _error(request, exc)
        else:
            _audit(request, "user.delete", username)
            messages.success(
                request,
                f"Usuario {username} excluido, com a conta Samba e a pasta home.",
            )
        return redirect("users")


class GroupDeleteView(AgentPostView):
    def post(self, request):
        name = request.POST.get("name", "")
        try:
            agent.delete_group(name)
        except AgentError as exc:
            _error(request, exc)
        else:
            _audit(request, "group.delete", name)
            messages.success(request, f"Grupo {name} excluido.")
        return redirect("users")


class SharesView(AgentTemplateView):
    template_name = "shares.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"agent_error": None, "shares": []})
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
        return context


class ShareCreateView(AgentFormView):
    template_name = "share_form.html"
    form_class = ShareCreateForm
    success_url = reverse_lazy("shares")

    def form_valid(self, form):
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
        except AgentError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        _audit(
            self.request,
            "share.create",
            data["name"],
            f"path={data['path']} snapshot={data.get('snapshot', False)} "
            f"private={data.get('private', False)}",
        )
        messages.success(self.request, f"Share {data['name']} criado.")
        return super().form_valid(form)


class SnapshotsView(AgentTemplateView):
    template_name = "snapshots.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"agent_error": None, "shares": []})
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
            context["shares"] = sorted(
                result, key=lambda item: item.get("share", "")
            )
            context["summary"] = {
                "total": len(result),
                "enabled": sum(1 for item in result if item.get("enabled")),
                "count": sum(int(item.get("count") or 0) for item in result),
                "size": sum(int(item.get("size") or 0) for item in result),
            }
        except AgentError as exc:
            context["agent_error"] = str(exc)
        return context


class SnapshotCreateView(AgentPostView):
    def post(self, request):
        share = request.POST.get("share", "")
        try:
            result = agent.snapshot_create(share)
        except AgentError as exc:
            _error(request, exc)
        else:
            _audit(
                request,
                "snapshot.create",
                f"{share}/{result.get('name', '')}",
            )
            messages.success(
                request,
                f"Snapshot criado para {share}: {result.get('name', '')}",
            )
        return redirect("snapshots")


class SnapshotDeleteView(AgentPostView):
    def post(self, request):
        share = request.POST.get("share", "")
        name = request.POST.get("name", "")
        try:
            agent.snapshot_delete(share, name)
        except AgentError as exc:
            _error(request, exc)
        else:
            _audit(request, "snapshot.delete", f"{share}/{name}")
            messages.success(request, f"Snapshot removido: {share}/{name}")
        return redirect("snapshots")
