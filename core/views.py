from __future__ import annotations

import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy

from .agent import AgentError, agent
from .credenciais import urls_usuario
from .forms import (
    GroupCreateForm,
    GroupsForm,
    PasswordForm,
    ShareCreateForm,
    SnapshotPolicyForm,
    UserCreateForm,
)
from .disk_table import enrich_disk_rows
from .hostinfo import anexar_discos, disk_role, volume_for
from .http import agent_json_error
from .models import AuditLog
from .tarefas import com_tarefa, disparo
from .view_base import AgentFormView, AgentPostView, AgentTemplateView, AgentView


def _anexar_discos(itens, chave="path"):
    """Associa cada item ao disco do mount. Falha do cache de discos não esconde a lista."""
    try:
        overview = agent.storage_overview()
    except AgentError:
        overview = None
    discos = overview.get("disks") if isinstance(overview, dict) else None
    return anexar_discos(itens, discos if isinstance(discos, list) else [], chave)


def _campo_rota(partes, flag):
    if flag not in partes:
        return "—"
    indice = partes.index(flag)
    if indice + 1 >= len(partes):
        return "—"
    return partes[indice + 1]


def parse_routes(linhas):
    rotas = []
    for linha in linhas or []:
        if isinstance(linha, dict):
            rotas.append(linha)
            continue
        texto = (linha or "").strip()
        if not texto:
            continue
        partes = texto.split()
        rotas.append(
            {
                "destination": partes[0],
                "via": _campo_rota(partes, "via"),
                "interface": _campo_rota(partes, "dev"),
                "source": _campo_rota(partes, "src"),
                "metric": _campo_rota(partes, "metric"),
            }
        )
    return rotas


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
            disk["role"] = disk_role(
                disk,
                settings.STORAGE_ROOT,
                settings.BACKUP_ROOT,
                settings.JELLYFIN_ROOT,
            )
        enrich_disk_rows(
            storage.get("disks", []),
            raid=storage.get("raid"),
            volumes=volumes,
            storage_root=settings.STORAGE_ROOT,
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
        _anexar_discos(context["shares"])
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
        elif "resync" in mdstat or "recovery" in mdstat:
            context["raid_status"] = "sincronizando"
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
        context.update(
            {
                "data": None,
                "error": None,
                "firewall": None,
                "firewall_error": None,
                "pode_gerenciar_firewall": settings.FIREWALL_MANAGE,
            }
        )
        try:
            data = agent.network_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        else:
            data["routes"] = parse_routes(data.get("routes"))
            context["data"] = data
        try:
            context["firewall"] = agent.firewall_overview()
        except AgentError as exc:
            context["firewall_error"] = str(exc)
        return context


class FirewallActionView(AgentPostView):
    def post(self, request):
        if not settings.FIREWALL_MANAGE:
            _error(request, "A gestão do firewall está desativada neste host.")
            return redirect("network_index")
        acao = (request.POST.get("acao") or "").strip()
        try:
            if acao == "enable":
                allow_ssh = request.POST.get("allow_ssh") == "1"
                agent.firewall_enable(allow_ssh=allow_ssh)
                _audit(request, "firewall.enable", detail=f"allow_ssh={allow_ssh}")
                messages.success(request, "Firewall ativado.")
            elif acao == "disable":
                agent.firewall_disable()
                _audit(request, "firewall.disable")
                messages.success(request, "Firewall desativado.")
            elif acao == "add":
                rule_action = (request.POST.get("rule_action") or "").strip()
                port = (request.POST.get("port") or "").strip()
                proto = (request.POST.get("proto") or "tcp").strip()
                source = (request.POST.get("source") or "").strip()
                agent.firewall_add_rule(
                    action=rule_action,
                    port=port,
                    proto=proto,
                    source=source,
                )
                _audit(
                    request,
                    "firewall.add",
                    target=f"{port}/{proto}",
                    detail=f"{rule_action} from={source or 'any'}",
                )
                messages.success(request, "Regra adicionada.")
            elif acao == "delete":
                spec = (request.POST.get("spec") or "").strip()
                agent.firewall_delete_rule(spec)
                _audit(request, "firewall.delete", target=spec)
                messages.success(request, "Regra removida.")
            else:
                _error(request, "Ação de firewall inválida.")
        except AgentError as exc:
            _error(request, exc)
        return redirect("network_index")


class ContainersView(AgentTemplateView):
    template_name = "containers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"overview": None, "error": None})
        context["app_container"] = settings.APP_CONTAINER
        try:
            context["overview"] = agent.containers_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        return context


class ContainerActionView(AgentPostView):
    def post(self, request):
        name = (request.POST.get("name") or "").strip()
        action = (request.POST.get("action") or "").strip()
        if action not in ("start", "stop", "restart"):
            _error(request, "Ação inválida.")
            return redirect("containers")
        if name == settings.APP_CONTAINER:
            _error(
                request,
                "Este é o container do próprio painel. Use o host para pará-lo ou reiniciá-lo.",
            )
            return redirect("containers")
        try:
            agent.container_action(name, action)
        except AgentError as exc:
            _error(request, exc)
        else:
            _audit(request, f"container.{action}", name)
            messages.success(request, f"Container {name}: {action} concluído.")
        return redirect("containers")


class ContainerLogsView(AgentView):
    def get(self, request):
        name = (request.GET.get("name") or "").strip()
        try:
            tail = int(request.GET.get("tail") or 200)
        except (TypeError, ValueError):
            tail = 200
        tail = max(1, min(tail, 1000))
        q = {"filtro": "container", "name": name, "tail": str(tail)}
        return redirect(f"{reverse('system_logs')}?{urlencode(q)}")


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
            data = agent.share_sizes()
        except AgentError as exc:
            return agent_json_error(exc)
        if not isinstance(data, dict):
            data = {}
        shares = data.get("shares") or []
        return JsonResponse(
            {
                "pending": bool(data.get("pending")),
                "error": data.get("error") or "",
                "shares": [
                    {
                        "name": item.get("name"),
                        "size": item.get("size"),
                        "size_snapshots": item.get("size_snapshots"),
                        "size_total": item.get("size_total"),
                    }
                    for item in shares
                ],
            }
        )


# Grupos de sistema (GID baixo ou nomes reservados do Linux). Não são share.
_CHIPS_SHARE_VISIVEIS = 2


_GRUPOS_SISTEMA = frozenset(
    {
        "adm",
        "audio",
        "backup",
        "bin",
        "bluetooth",
        "cdrom",
        "crontab",
        "daemon",
        "dialout",
        "dip",
        "disk",
        "docker",
        "fax",
        "floppy",
        "games",
        "gpio",
        "i2c",
        "input",
        "kvm",
        "lp",
        "lpadmin",
        "lxd",
        "mail",
        "man",
        "messagebus",
        "netdev",
        "nogroup",
        "operator",
        "plugdev",
        "render",
        "root",
        "sambashare",
        "scanner",
        "shadow",
        "spi",
        "src",
        "ssh",
        "staff",
        "sudo",
        "sys",
        "systemd-journal",
        "tape",
        "tty",
        "users",
        "utmp",
        "video",
        "voice",
        "wheel",
        "www-data",
    }
)


def _pessoas_e_grupos(users, nomes):
    """Separa grupo privado, grupo de share e grupo de sistema."""
    contas = {item["username"] for item in users}
    share_nomes = [
        nome for nome in nomes if nome not in contas and nome not in _GRUPOS_SISTEMA
    ]
    sistema_nomes = [
        nome for nome in nomes if nome not in contas and nome in _GRUPOS_SISTEMA
    ]
    membros = {nome: [] for nome in share_nomes + sistema_nomes}
    pessoas = []
    for item in users:
        share = []
        sistema = []
        for grupo in item.get("groups") or []:
            if grupo in contas:
                continue
            if grupo in _GRUPOS_SISTEMA:
                sistema.append(grupo)
            else:
                share.append(grupo)
            if grupo in membros:
                membros[grupo].append(item["username"])
        visivel = share[:_CHIPS_SHARE_VISIVEIS]
        extra = len(share) - len(visivel)
        registro = {
            **item,
            "share_groups": share,
            "share_groups_visible": visivel,
            "share_groups_extra": extra,
            "system_groups": sistema,
            "initial": (item.get("username") or "?")[:1].upper(),
        }
        if settings.CREDENTIALS_MANAGE_USERS:
            links = urls_usuario(item["username"])
            registro.update(
                {
                    "credenciais_senha": links.get("senha", ""),
                    "credenciais_grupos": links.get("grupos", ""),
                    "credenciais_conta": links.get("conta", ""),
                }
            )
        pessoas.append(registro)

    def pacote(lista, sistema):
        return [
            {"name": nome, "members": membros[nome], "system": sistema}
            for nome in lista
        ]

    return pessoas, pacote(share_nomes, False), pacote(sistema_nomes, True)


class UsersView(AgentTemplateView):
    template_name = "users.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"agent_error": None, "users": [], "groups": [], "system_groups": []})
        try:
            users = agent.list_users()
        except AgentError as exc:
            context["agent_error"] = str(exc)
            return context
        try:
            nomes = agent.list_groups()
        except AgentError as exc:
            context["agent_error"] = str(exc)
            return context
        pessoas, grupos, sistema = _pessoas_e_grupos(users, nomes)
        context["users"] = pessoas
        context["groups"] = grupos
        context["system_groups"] = sistema
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
            shares = agent.list_shares(include_size=False)
            snap_by_name = {
                item.get("share"): item
                for item in agent.snapshot_usage(include_size=False)
            }
            for share in shares:
                snap = snap_by_name.get(share.get("name"))
                share["snapshot_enabled"] = bool(snap and snap.get("enabled"))
                share["snapshot_keep"] = snap.get("keep") if snap else None
                share["snapshot_count"] = snap.get("count") if snap else 0
            _anexar_discos(shares)
            context["shares"] = shares
        except AgentError as exc:
            context["agent_error"] = str(exc)
        try:
            context["agenda"] = agent.versoes_schedule()
        except AgentError:
            context["agenda"] = None
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


class TaskStatusView(AgentView):
    def get(self, request, task_id):
        if not re.fullmatch(r"[a-z0-9]+-[a-f0-9]{8}", task_id or ""):
            return JsonResponse(
                {"status": "failed", "message": "Tarefa invalida.", "result": {}}
            )
        try:
            dados = agent.task_status(task_id)
        except AgentError as exc:
            return JsonResponse(
                {"status": "failed", "message": str(exc), "result": {}}
            )
        if not isinstance(dados, dict):
            dados = {}
        resultado = dados.get("result")
        return JsonResponse(
            {
                "status": dados.get("status") or "failed",
                "message": dados.get("message") or "",
                "op": dados.get("op") or "",
                "result": resultado if isinstance(resultado, dict) else {},
            }
        )


class SnapshotsView(AgentTemplateView):
    template_name = "snapshots.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"agent_error": None, "shares": []})
        try:
            policies = {
                item.get("share"): item
                for item in agent.snapshot_usage(include_size=False)
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
                        "configured": False,
                    }
                else:
                    item = {**item, "configured": True}
                result.append(item)
                seen.add(name)
            for name, item in policies.items():
                if name not in seen:
                    result.append({**item, "configured": True})
            context["shares"] = _anexar_discos(
                sorted(result, key=lambda item: item.get("share", ""))
            )
            context["summary"] = {
                "total": len(result),
                "enabled": sum(1 for item in result if item.get("enabled")),
                "count": sum(int(item.get("count") or 0) for item in result),
                "size": sum(int(item.get("size") or 0) for item in result),
            }
        except AgentError as exc:
            context["agent_error"] = str(exc)
        try:
            context["agenda"] = agent.versoes_schedule()
        except AgentError:
            context["agenda"] = None
        return context


class SnapshotPolicyView(AgentView):
    template_name = "snapshot_policy.html"

    def get(self, request, share=None):
        try:
            shares, politicas = self._dados()
        except AgentError as exc:
            return self._render(request, agent_error=str(exc))
        if share and not self._share_conhecido(share, shares, politicas):
            messages.error(request, f"Share {share} não encontrado.")
            return redirect("snapshots")
        return self._render(request, share=share, shares=shares, politicas=politicas)

    def post(self, request, share=None):
        try:
            shares, politicas = self._dados()
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("snapshots")
        if share and not self._share_conhecido(share, shares, politicas):
            messages.error(request, f"Share {share} não encontrado.")
            return redirect("snapshots")
        form, _politica = self._form(
            share, shares, politicas, data=request.POST
        )
        if form is None or not form.is_valid():
            return self._render(
                request,
                share=share,
                shares=shares,
                politicas=politicas,
                data=request.POST,
            )
        alvo = share or form.cleaned_data["share"]
        if not self._share_conhecido(alvo, shares, politicas):
            form.add_error("share", "Share não encontrado.")
            return self._render(
                request,
                share=share,
                shares=shares,
                politicas=politicas,
                form=form,
            )
        confirmacao = (request.POST.get("confirmation") or "").strip()
        try:
            resultado = agent.snapshot_policy_save(
                share=alvo,
                enabled=bool(form.cleaned_data.get("enabled")),
                keep=form.cleaned_data["keep"],
                create_now=bool(form.cleaned_data.get("create_now")),
                confirmation=confirmacao,
            )
        except AgentError as exc:
            mensagem = str(exc)
            converter = "campo de confirmação" in mensagem
            if not converter:
                form.add_error(None, mensagem)
            return self._render(
                request,
                share=share,
                shares=shares,
                politicas=politicas,
                form=form,
                converter=converter,
                confirmacao_share=alvo if converter else "",
                converter_aviso=mensagem if converter else "",
            )
        task = disparo(request, resultado, action="snapshot.policy", target=alvo)
        return redirect(com_tarefa(reverse("snapshots"), task))

    def _dados(self):
        shares = agent.list_shares(include_size=False)
        politicas = {
            item.get("share"): item
            for item in agent.snapshot_usage(include_size=False)
        }
        return shares, politicas

    def _share_conhecido(self, share, shares, politicas):
        nomes = {item.get("name") for item in shares}
        return share in nomes or share in politicas

    def _form(self, share, shares, politicas, data=None):
        politica = politicas.get(share) if share else None
        if share:
            return (
                SnapshotPolicyForm(
                    data,
                    lock_share=share,
                    show_create_now=politica is None,
                    initial={
                        "share": share,
                        "keep": (politica or {}).get("keep") or 7,
                        "enabled": True if politica is None else bool(politica.get("enabled")),
                    },
                ),
                politica,
            )
        livres = [
            (item.get("name"), f"{item.get('name')} — {item.get('path') or ''}")
            for item in shares
            if item.get("name") and item.get("name") not in politicas
        ]
        if data is None and not livres:
            return None, None
        return (
            SnapshotPolicyForm(
                data,
                share_choices=livres,
                show_create_now=True,
                initial={"keep": 7, "enabled": True},
            ),
            None,
        )

    def _render(
        self,
        request,
        *,
        share=None,
        shares=None,
        politicas=None,
        data=None,
        form=None,
        agent_error=None,
        converter=False,
        confirmacao_share="",
        converter_aviso="",
    ):
        shares = shares or []
        politicas = politicas or {}
        if form is None and agent_error is None:
            form, _politica = self._form(share, shares, politicas, data=data)
        politica = politicas.get(share) if share else None
        if share and politica:
            modo = "editar"
        elif share:
            modo = "configurar"
        else:
            modo = "nova"
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "modo": modo,
                "share": share,
                "agent_error": agent_error,
                "sem_share": form is None and agent_error is None,
                "sem_compartilhamento": not shares and not share,
                "converter": converter,
                "confirmacao_share": confirmacao_share,
                "converter_aviso": converter_aviso,
            },
        )


class SnapshotCreateView(AgentPostView):
    def post(self, request):
        share = request.POST.get("share", "")
        try:
            result = agent.snapshot_create(share)
        except AgentError as exc:
            _error(request, exc)
            return redirect("snapshots")
        task = disparo(request, result, action="snapshot.create", target=share)
        return redirect(com_tarefa(reverse("snapshots"), task))


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


class SnapshotRestoreView(AgentPostView):
    def post(self, request):
        share = request.POST.get("share", "")
        name = request.POST.get("name", "")
        confirmacao = (request.POST.get("confirmation") or "").strip()
        if confirmacao != name:
            messages.error(
                request,
                "Para restaurar, digite o nome do snapshot exatamente como aparece.",
            )
            return redirect("snapshots")
        try:
            resultado = agent.snapshot_restore(share, name, confirmation=confirmacao)
        except AgentError as exc:
            _error(request, exc)
            return redirect("snapshots")
        task = disparo(
            request, resultado, action="snapshot.restore", target=f"{share}/{name}"
        )
        return redirect(com_tarefa(reverse("snapshots"), task))
