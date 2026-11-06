"""Telas do menu Sistema: host, chaves, logs, serviços e terminal."""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from .agent import AgentError, agent
from .context_processors import capacidades_do_host
from .models import AuditLog, token_da_api
from .tarefas import com_tarefa, disparo
from .view_base import AgentPostView, AgentTemplateView, AgentView

UNIT_DENY = frozenset(
    {
        "ssh",
        "sshd",
        "homelab-storage-agent",
        "docker",
        "containerd",
        "podman",
        "systemd-journald",
        "systemd-networkd",
    }
)
UNIT_RE = re.compile(r"^[a-zA-Z0-9:_.@\-]+$")
LOG_FILTERS = ("sistema", "storage", "rede", "servico", "container")
J_PRIORITIES = (
    "emerg",
    "alert",
    "crit",
    "err",
    "warning",
    "notice",
    "info",
    "debug",
)
J_PERIODS = ("1h", "24h", "7d")


def _audit(request, action, target="", detail=""):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        target=target,
        detail=detail,
        ip=request.META.get("REMOTE_ADDR"),
    )


def _cap(name: str) -> bool:
    return bool(capacidades_do_host().get(name))


def _system_manage_effetivo() -> bool:
    return settings.SYSTEM_MANAGE and _cap("system_manage")


def _torrent_fp_sha256() -> str:
    tok = token_da_api() or ""
    if not tok:
        return ""
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()


def _validar_unit_para_acao(unit: str) -> str | None:
    u = (unit or "").strip()
    if not u or not UNIT_RE.fullmatch(u):
        return "Nome da unit inválido."
    base = u.split("@", 1)[0].removesuffix(".service")
    if base in UNIT_DENY:
        return "Esta unit não pode ser alterada por política de segurança."
    return None


class SystemHostView(AgentView):
    template_name = "system_host.html"
    http_method_names = ["get", "head", "post"]

    def get(self, request):
        context = {
            "host_info": None,
            "host_error": None,
            "apt_cap": _cap("apt"),
            "apt_manage": _cap("apt") and _system_manage_effetivo(),
        }
        try:
            context["host_info"] = agent.host_info()
        except AgentError as exc:
            context["host_error"] = str(exc)
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        if request.POST.get("acao") == "apt_upgrade":
            return self._apt_upgrade(request)
        if request.POST.get("acao") == "apt_check":
            return self._apt_check(request)
        messages.error(request, "Ação inválida.")
        return redirect("system_host")

    def _apt_check(self, request):
        if not (_cap("apt") and _system_manage_effetivo()):
            messages.error(request, "A verificação de pacotes não está disponível.")
            return redirect("system_host")
        try:
            resultado = agent.apt_check()
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("system_host")
        task = disparo(request, resultado, action="apt.check", target="apt")
        _audit(request, "apt.check", "apt")
        destino = com_tarefa(reverse("system_host"), task)
        return redirect(destino)

    def _apt_upgrade(self, request):
        if not (_cap("apt") and _system_manage_effetivo()):
            messages.error(request, "A atualização de pacotes não está disponível.")
            return redirect("system_host")
        if (request.POST.get("confirmation") or "").strip() != "ATUALIZAR":
            messages.error(
                request,
                'Para confirmar, digite exatamente a palavra ATUALIZAR.',
            )
            return redirect("system_host")
        try:
            resultado = agent.apt_upgrade(confirmation="ATUALIZAR")
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("system_host")
        task = disparo(request, resultado, action="apt.upgrade", target="apt")
        _audit(request, "apt.upgrade", "apt")
        return redirect(com_tarefa(reverse("system_host"), task))


class SystemKeysView(AgentTemplateView):
    template_name = "system_keys.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "keys": [],
                "keys_error": None,
                "show_torrent_slot": _cap("jellyfin"),
                "torrent_token_presente": bool(token_da_api()),
                "torrent_fingerprint_sha256": _torrent_fp_sha256(),
            }
        )
        try:
            dados = agent.ssh_keys()
            context["keys"] = dados.get("keys") or [] if isinstance(dados, dict) else []
        except AgentError as exc:
            context["keys_error"] = str(exc)
        return context


class SystemLogsView(AgentTemplateView):
    template_name = "system_logs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        filtro = (params.get("filtro") or "sistema").strip().lower()
        prioridade = (params.get("prioridade") or "info").strip().lower()
        periodo = (params.get("periodo") or "1h").strip().lower()
        unit = (params.get("unit") or "").strip()
        name = (params.get("name") or "").strip()
        tail_s = (params.get("tail") or "200").strip()
        try:
            tail = int(tail_s)
        except ValueError:
            tail = 200
        tail = max(1, min(tail, 500))
        overview = None
        if _cap("containers"):
            try:
                overview = agent.containers_overview()
            except AgentError:
                overview = None
        containers = []
        if isinstance(overview, dict):
            for item in overview.get("containers") or []:
                if isinstance(item, dict) and item.get("name"):
                    containers.append(item["name"])
        context.update(
            {
                "filtro": filtro,
                "prioridade": prioridade,
                "periodo": periodo,
                "unit": unit,
                "name": name,
                "tail": tail,
                "linhas": [],
                "journal_error": None,
                "journal_cap": _cap("journal"),
                "containers_cap": _cap("containers"),
                "container_names": sorted(set(containers)),
                "filtros_disponiveis": [
                    f
                    for f in LOG_FILTERS
                    if f != "container" or _cap("containers")
                ],
            }
        )
        if not _cap("journal") and filtro != "container":
            context["journal_error"] = (
                "O journalctl não está disponível neste host."
            )
            return context
        if filtro == "container" and not _cap("containers"):
            context["journal_error"] = (
                "Não há runtime de container; o filtro Container foi ocultado."
            )
            return context
        if filtro not in LOG_FILTERS:
            context["journal_error"] = "Filtro de log desconhecido."
            return context
        if filtro == "container" and not name:
            context["journal_error"] = "Escolha um container."
            return context
        if filtro == "sistema":
            if prioridade not in J_PRIORITIES:
                context["journal_error"] = "Prioridade inválida."
                return context
            if periodo not in J_PERIODS:
                context["journal_error"] = "Período inválido."
                return context
        try:
            dados = agent.journal(
                filtro=filtro,
                prioridade=prioridade,
                periodo=periodo,
                unit=unit,
                name=name,
                tail=tail,
            )
        except AgentError as exc:
            context["journal_error"] = str(exc)
            return context
        if isinstance(dados, dict) and "lines" in dados:
            context["linhas"] = dados["lines"]
        elif isinstance(dados, dict) and "logs" in dados:
            texto = dados.get("logs") or ""
            context["linhas"] = texto.splitlines()[-tail:]
        return context


class ContainerLogsRedirectView(AgentView):
    def get(self, request):
        nome = (request.GET.get("name") or "").strip()
        tail = (request.GET.get("tail") or "200").strip()
        q = {"filtro": "container", "name": nome, "tail": tail}
        return redirect(f"{reverse('system_logs')}?{urlencode(q)}")


class SystemServicesView(AgentTemplateView):
    template_name = "system_services.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "units": [],
                "units_error": None,
                "systemctl_cap": _cap("systemctl"),
                "pode_agir": _cap("systemctl") and _system_manage_effetivo(),
            }
        )
        if not _cap("systemctl"):
            context["units_error"] = "O systemd não está disponível neste host."
            return context
        try:
            dados = agent.systemd_list_units()
            context["units"] = dados.get("units") or []
        except AgentError as exc:
            context["units_error"] = str(exc)
        return context


class SystemServiceActionView(AgentPostView):
    def post(self, request):
        unit = (request.POST.get("unit") or "").strip()
        action = (request.POST.get("action") or "").strip().lower()
        erro = _validar_unit_para_acao(unit)
        if erro:
            messages.error(request, erro)
            return redirect("system_services")
        if action not in {"start", "stop", "restart", "enable", "disable"}:
            messages.error(request, "Ação inválida.")
            return redirect("system_services")
        if not (_cap("systemctl") and _system_manage_effetivo()):
            messages.error(request, "Esta ação está desativada neste host.")
            return redirect("system_services")
        if action in {"stop", "restart", "disable"}:
            if (request.POST.get("confirmation") or "").strip() != unit:
                messages.error(
                    request,
                    "Para confirmar, digite exatamente o nome da unit.",
                )
                return redirect("system_services")
        try:
            agent.systemd_unit_action(unit=unit, action=action)
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("system_services")
        _audit(request, f"systemd.{action}", unit)
        messages.success(request, f"Unit {unit}: {action} concluído.")
        return redirect("system_services")


class TerminalPageView(AgentTemplateView):
    template_name = "system_terminal.html"

    def dispatch(self, request, *args, **kwargs):
        if not (settings.TERMINAL_ENABLE and _cap("terminal_enable")):
            return HttpResponseNotFound("Terminal desativado neste host.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["terminal_socket_path"] = settings.TERMINAL_SOCKET
        return context


class TerminalIoView(AgentView):
    def dispatch(self, request, *args, **kwargs):
        if not (settings.TERMINAL_ENABLE and _cap("terminal_enable")):
            return JsonResponse({"ok": False, "error": "Terminal desativado"}, status=404)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
        op = str(payload.get("op") or "").strip()
        try:
            if op == "open":
                usuario = str(payload.get("user") or "").strip()
                senha = str(payload.get("password") or "")
                if not usuario or not senha:
                    return JsonResponse(
                        {"ok": False, "error": "Informe o usuário Linux e a senha sudo."},
                        status=400,
                    )
                dados = agent.terminal_open(
                    cols=int(payload.get("cols") or 80),
                    rows=int(payload.get("rows") or 24),
                    user=usuario,
                    password=senha,
                )
                sid = dados.get("session_id") or ""
                _audit(self.request, "terminal.open", usuario, sid[:16])
                return JsonResponse({"ok": True, "data": dados})
            if op == "io":
                dados = agent.terminal_io(
                    session_id=str(payload.get("session_id") or ""),
                    input_b64=str(payload.get("input_b64") or ""),
                )
                return JsonResponse({"ok": True, "data": dados})
            if op == "close":
                sid = str(payload.get("session_id") or "")
                dados = agent.terminal_close(session_id=sid)
                _audit(self.request, "terminal.close", sid[:16])
                return JsonResponse({"ok": True, "data": dados})
        except AgentError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": False, "error": "op inválida"}, status=400)
