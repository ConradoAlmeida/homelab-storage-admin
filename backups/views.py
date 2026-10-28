from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from core.agent import AgentError, agent
from core.http import file_response
from core.models import AuditLog
from core.view_base import AgentPostView, AgentTemplateView, AgentView

from .defaults import DEFAULT_EXCLUDES_TEXT

LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
WEEKDAY_LABELS = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
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


def _snapshot_browse_url(snapshot_id: str, disk_uuid: str, path: str) -> str:
    base = reverse("backup_snapshot_browse", args=[snapshot_id])
    return f"{base}?{urlencode({'disk_uuid': disk_uuid, 'path': path})}"


def _snapshot_download_url(snapshot_id: str, disk_uuid: str, path: str) -> str:
    base = reverse("backup_snapshot_download", args=[snapshot_id])
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


def _gitea_error_text(erro: str) -> str:
    texto = (erro or "").strip()
    baixo = texto.lower()
    if "input/output error" in baixo or "errno 5" in baixo:
        return (
            "O drive USB desconectou ou falhou durante a cópia/verificação. "
            "O dump no servidor foi gerado e está íntegro; tente com outro drive "
            "ou outra porta USB."
        )
    if "no space" in baixo or "espaco insuficiente" in baixo:
        return (
            "Espaço insuficiente no drive USB. "
            "O dump no servidor está íntegro."
        )
    if "nao confere" in baixo:
        return (
            "A cópia no USB não confere com o dump. O dump no servidor está "
            "íntegro; tente de novo com o drive conectado."
        )
    if "nao encontrado" in baixo and "usb" in baixo:
        return "O drive USB não foi encontrado. Conecte-o e tente de novo."
    return texto or "Falha no backup."


def _algum_rodando(overview) -> bool:
    if not isinstance(overview, dict):
        return False
    for item in overview.get("jobs") or []:
        if not isinstance(item, dict):
            continue
        if (item.get("status") or {}).get("status") == "running":
            return True
    return False


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


class BackupIndexView(AgentTemplateView):
    template_name = "backups/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "overview": None,
                "error": None,
                "arquivos": None,
                "arquivos_error": None,
            }
        )
        try:
            context["overview"] = agent.backup_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        if context.get("overview"):
            discs = context["overview"].get("disks", [])
            context["tem_disco_backup"] = any(
                item.get("configured") for item in discs
            )
            context["tem_candidato"] = any(item.get("candidate") for item in discs)
        try:
            context["arquivos"] = agent.arquivos_jobs()
        except AgentError as exc:
            context["arquivos_error"] = str(exc)
        context["rodando"] = _algum_rodando(
            context.get("overview")
        ) or _algum_rodando(context.get("arquivos"))
        return context


class BackupSnapshotsView(AgentTemplateView):
    template_name = "backups/snapshots.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"snapshots": [], "errors": [], "error": None})
        try:
            data = agent.backup_snapshots()
            context["snapshots"] = data.get("snapshots", [])
            context["errors"] = data.get("errors", [])
        except AgentError as exc:
            context["error"] = str(exc)
        return context


class ResticSnapshotBrowseView(AgentView):
    def get(self, request, snapshot_id):
        disk_uuid = (request.GET.get("disk_uuid") or "").strip()
        path = (request.GET.get("path") or "/mnt/nas").strip()
        query = (request.GET.get("q") or "").strip()
        context = {
            "snapshot_id": snapshot_id,
            "snapshot": {},
            "disk_uuid": disk_uuid,
            "path": path,
            "query": query,
            "parent": str(PurePosixPath(path).parent),
            "breadcrumbs": _snapshot_breadcrumbs(path),
            "entries": [],
            "search_matches": [],
            "search_total": 0,
            "search_truncated": False,
            "search_action": reverse(
                "backup_snapshot_browse", args=[snapshot_id]
            ),
            "search_clear_url": _snapshot_browse_url(
                snapshot_id, disk_uuid, path
            ),
            "search_hidden": [
                {"name": "disk_uuid", "value": disk_uuid},
                {"name": "path", "value": path},
            ],
            "search_placeholder": "Buscar nome ou caminho no snapshot inteiro",
            "error": None,
        }
        if query:
            try:
                data = agent.backup_search(disk_uuid, snapshot_id, query)
            except AgentError as exc:
                context["error"] = str(exc)
            else:
                matches = []
                for match in data.get("matches") or []:
                    is_dir = match.get("type") == "dir"
                    match_path = match.get("path") or ""
                    parent = match.get("parent") or str(
                        PurePosixPath(match_path).parent
                    )
                    matches.append(
                        {
                            **match,
                            "rel": match_path,
                            "is_dir": is_dir,
                            "browse_url": _snapshot_browse_url(
                                snapshot_id,
                                disk_uuid,
                                match_path if is_dir else parent,
                            ),
                            "download_url": None
                            if is_dir
                            else _snapshot_download_url(
                                snapshot_id, disk_uuid, match_path
                            ),
                            "versions_url": None,
                            "mtime_text": match.get("mtime") or "—",
                        }
                    )
                context.update(
                    {
                        "snapshot_id": data.get("snapshot_id") or snapshot_id,
                        "query": data.get("query") or query,
                        "search_matches": matches,
                        "search_total": data.get("total", 0),
                        "search_truncated": bool(data.get("truncated")),
                        "search_action": reverse(
                            "backup_snapshot_browse", args=[snapshot_id]
                        ),
                        "search_clear_url": _snapshot_browse_url(
                            snapshot_id, disk_uuid, path
                        ),
                        "search_hidden": [
                            {"name": "disk_uuid", "value": disk_uuid},
                            {"name": "path", "value": path},
                        ],
                        "search_placeholder": "Buscar nome ou caminho no snapshot inteiro",
                    }
                )
            return render(request, "backups/snapshot_browse.html", context)

        try:
            data = agent.backup_ls(disk_uuid, snapshot_id, path)
        except AgentError as exc:
            context["error"] = str(exc)
        else:
            context.update(
                {
                    "snapshot_id": data.get("snapshot_id") or snapshot_id,
                    "snapshot": data.get("snapshot") or {},
                    "path": data.get("path") or path,
                    "parent": data.get("parent") or context["parent"],
                    "breadcrumbs": _snapshot_breadcrumbs(data.get("path") or path),
                    "entries": data.get("entries") or [],
                }
            )
        return render(request, "backups/snapshot_browse.html", context)


class ResticSnapshotDownloadView(AgentView):
    def get(self, request, snapshot_id):
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

        AuditLog.objects.create(
            actor=request.user,
            action="backup_snapshot_download",
            target=snapshot_id,
            detail=path,
            ip=request.META.get("REMOTE_ADDR"),
        )
        return file_response(target, result.get("filename") or target.name)


class BackupCheckView(AgentPostView):
    def post(self, request):
        uuid = (request.POST.get("uuid") or "").strip()
        try:
            resultado = agent.backup_check(uuid)
        except AgentError as exc:
            messages.error(request, f"Verificacao do repositorio falhou: {exc}")
        else:
            if resultado.get("ok"):
                messages.success(
                    request,
                    "Repositorio integro. "
                    f"Verificado em {resultado.get('finished_at')}.",
                )
            else:
                messages.error(
                    request,
                    "O restic encontrou problemas: "
                    f"{resultado.get('message', '')[:400]}",
                )
            AuditLog.objects.create(
                actor=request.user,
                action="backup_check",
                target=uuid,
                detail=f"ok={resultado.get('ok')}",
                ip=request.META.get("REMOTE_ADDR"),
            )
        return redirect("backup_index")


class DiskWizardView(AgentView):
    template_name = "backups/disk_wizard.html"

    def _overview(self, request):
        try:
            return agent.backup_overview(), None
        except AgentError as exc:
            return None, str(exc)

    def get(self, request):
        overview, error = self._overview(request)
        if error:
            return render(
                request,
                self.template_name,
                {"overview": None, "selected": None, "error": error},
            )
        device = (request.GET.get("device") or "").strip()
        if not device:
            return redirect("backup_index")
        selected = next(
            (disk for disk in overview.get("disks", []) if disk["path"] == device),
            None,
        )
        if selected is None:
            return render(
                request,
                self.template_name,
                {
                    "overview": overview,
                    "selected": None,
                    "error": f"Disco nao encontrado: {device}",
                },
            )
        if (
            selected["extra_confirmation"]
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
            self.template_name,
            {
                "overview": overview,
                "selected": selected,
                "error": None,
                "default_label": _default_label(selected),
            },
        )

    def post(self, request):
        overview, error = self._overview(request)
        if error:
            return render(
                request,
                self.template_name,
                {"overview": None, "selected": None, "error": error},
            )
        device = (request.POST.get("device") or "").strip()
        if not device:
            return redirect("backup_index")
        selected = next(
            (disk for disk in overview.get("disks", []) if disk["path"] == device),
            None,
        )
        if selected is None:
            return render(
                request,
                self.template_name,
                {
                    "overview": overview,
                    "selected": None,
                    "error": f"Disco nao encontrado: {device}",
                },
            )

        password = request.POST.get("password") or ""
        label = (request.POST.get("label") or "").strip().lower()
        confirmation = request.POST.get("confirmation") or ""
        acknowledge = request.POST.get("acknowledge") == "1"
        error = None
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
        return render(
            request,
            self.template_name,
            {
                "overview": overview,
                "selected": selected,
                "error": error,
                "default_label": _default_label(selected),
            },
        )


class CredentialsView(AgentView):
    template_name = "backups/credentials.html"

    def _context(self, request):
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
            return context
        context["overview"] = overview
        context["disks"] = [
            disk for disk in overview.get("disks", []) if disk.get("configured")
        ]
        return context

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        context = self._context(request)
        if context["error"]:
            return render(request, self.template_name, context)
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
        return render(request, self.template_name, context)


class JobFormView(AgentView):
    template_name = "backups/job_form.html"

    def _context(self, request, name=None):
        try:
            overview = agent.backup_overview()
        except AgentError as exc:
            return None, {
                "overview": None,
                "error": str(exc),
                "disks": [],
                "shares": [],
            }
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
                return None, None
        context = {
            "overview": overview,
            "disks": disks,
            "shares": shares,
            "shares_error": shares_error,
            "weekdays": WEEKDAYS,
            "job": job,
            "error": None,
            "default_excludes_text": DEFAULT_EXCLUDES_TEXT,
        }
        return job, context

    def get(self, request, name=None):
        job, context = self._context(request, name)
        if context is None:
            return redirect("backup_index")
        if job is not None:
            context["form"] = _job_form_from_job(job)
        else:
            context["form"] = _default_job_form(context["overview"])
        return render(request, self.template_name, context)

    def post(self, request, name=None):
        job, context = self._context(request, name)
        if context is None:
            return redirect("backup_index")
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
        context["form"] = form
        if not form_name:
            context["error"] = "Informe o nome do job."
        elif job is None and any(
            item.get("name") == form_name
            for item in context["overview"].get("jobs", [])
        ):
            context["error"] = "Já existe um job com esse nome; edite o existente."
        elif not context["disks"]:
            context["error"] = (
                "Nenhum disco de backup configurado. Prepare um disco primeiro."
            )
        elif not context["shares"]:
            context["error"] = "Nenhum share encontrado."
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
                context["error"] = str(exc)
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
        return render(request, self.template_name, context)


class JobRunView(AgentPostView):
    def post(self, request, name):
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
                request,
                f"Backup {name} iniciado. O andamento aparece neste painel automaticamente.",
            )
        return redirect("backup_index")


class JobToggleView(AgentPostView):
    def post(self, request, name):
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


class JobDeleteView(AgentPostView):
    def post(self, request, name):
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


class ColdIndexView(AgentTemplateView):
    template_name = "backups/cold_index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"overview": None, "error": None})
        try:
            context["overview"] = agent.cold_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        return context


class ColdPrepareView(AgentView):
    template_name = "backups/cold_prepare.html"

    def _overview(self, request):
        try:
            return agent.cold_overview(), None
        except AgentError as exc:
            return None, str(exc)

    def get(self, request):
        overview, error = self._overview(request)
        if error:
            return render(
                request,
                self.template_name,
                {"overview": None, "selected": None, "error": error},
            )
        device = (request.GET.get("device") or "").strip()
        if not device:
            return redirect("cold_index")
        selected = next(
            (disk for disk in overview.get("disks", []) if disk["path"] == device),
            None,
        )
        if selected is None:
            return render(
                request,
                self.template_name,
                {
                    "overview": overview,
                    "selected": None,
                    "error": f"Drive não encontrado: {device}",
                },
            )
        if (
            selected["extra_confirmation"]
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
            self.template_name,
            {
                "overview": overview,
                "selected": selected,
                "error": None,
                "default_label": _default_label(selected),
            },
        )

    def post(self, request):
        overview, error = self._overview(request)
        if error:
            return render(
                request,
                self.template_name,
                {"overview": None, "selected": None, "error": error},
            )
        device = (request.POST.get("device") or "").strip()
        if not device:
            return redirect("cold_index")
        selected = next(
            (disk for disk in overview.get("disks", []) if disk["path"] == device),
            None,
        )
        if selected is None:
            return render(
                request,
                self.template_name,
                {
                    "overview": overview,
                    "selected": None,
                    "error": f"Drive não encontrado: {device}",
                },
            )

        password = request.POST.get("password") or ""
        label = (request.POST.get("label") or "").strip().lower()
        confirmation = request.POST.get("confirmation") or ""
        acknowledge = request.POST.get("acknowledge") == "1"
        error = None
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
        return render(
            request,
            self.template_name,
            {
                "overview": overview,
                "selected": selected,
                "error": error,
                "default_label": _default_label(selected),
            },
        )


class ColdCopyView(AgentPostView):
    def post(self, request):
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


class ColdEjectView(AgentPostView):
    def post(self, request):
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
            messages.success(
                request, "Drive frio ejetado. Pode desconectar com segurança."
            )
        return redirect("cold_index")



class ArquivosJobsView(AgentTemplateView):
    template_name = "backups/arquivos_jobs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"overview": None, "error": None})
        try:
            context["overview"] = agent.arquivos_jobs()
        except AgentError as exc:
            context["error"] = str(exc)
        context["rodando"] = _algum_rodando(context.get("overview"))
        return context


class ArquivosJobView(AgentTemplateView):
    template_name = "backups/arquivos_job.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"detalhe": None, "error": None})
        try:
            context["detalhe"] = agent.arquivos_job(self.kwargs["job"])
        except AgentError as exc:
            context["error"] = str(exc)
        return context


TRABALHO_PADRAO = {
    "name": "",
    "label": "",
    "enabled": True,
    "time": "03:30",
    "frequency": "daily",
    "weekday": 0,
    "retention_days": 30,
    "sources": [],
}


class ArquivosJobFormView(AgentTemplateView):
    template_name = "backups/arquivos_job_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "job": dict(TRABALHO_PADRAO),
                "sources_text": "",
                "error": None,
                "weekdays": list(enumerate(WEEKDAY_LABELS)),
                "edicao": False,
            }
        )
        nome = self.kwargs.get("job")
        if nome:
            context["edicao"] = True
            try:
                detalhe = agent.arquivos_job(nome)
            except AgentError as exc:
                context["error"] = str(exc)
            else:
                context["job"] = detalhe["job"]
                context["sources_text"] = "\n".join(
                    fonte["path"] for fonte in detalhe["job"]["sources"]
                )
        return context

    def _formulario(self, request, job=None):
        linhas = (request.POST.get("sources") or "").splitlines()
        caminhos = [linha.strip() for linha in linhas if linha.strip()]
        return {
            "name": (request.POST.get("name") or job or "").strip(),
            "label": (request.POST.get("label") or "").strip(),
            "enabled": request.POST.get("enabled") == "1",
            "time": (request.POST.get("time") or "03:30").strip(),
            "frequency": request.POST.get("frequency") or "daily",
            "weekday": request.POST.get("weekday") or 0,
            "retention_days": request.POST.get("retention_days") or 30,
            "sources": [{"path": caminho} for caminho in caminhos],
        }

    def post(self, request, job=None):
        dados = self._formulario(request, job)
        try:
            detalhe = agent.arquivos_job_save(dados)
        except AgentError as exc:
            return render(
                request,
                self.template_name,
                {
                    "job": dados,
                    "sources_text": "\n".join(
                        fonte["path"] for fonte in dados["sources"]
                    ),
                    "error": str(exc),
                    "weekdays": list(enumerate(WEEKDAY_LABELS)),
                    "edicao": bool(job),
                },
            )
        AuditLog.objects.create(
            actor=request.user,
            action="arquivos_job_save",
            target=detalhe["job"]["name"],
            detail=f"{detalhe['job']['frequency']} {detalhe['job']['time']}",
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Job {detalhe['job']['label']} salvo.")
        return redirect("arquivos_job", job=detalhe["job"]["name"])


class ArquivosJobRunView(AgentPostView):
    def post(self, request, job):
        try:
            agent.arquivos_job_run(job)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel iniciar o backup: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="arquivos_job_run",
                target=job,
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(
                request,
                "Backup iniciado. O andamento aparece nesta página automaticamente.",
            )
        return redirect("arquivos_job", job=job)


class ArquivosJobDeleteView(AgentPostView):
    def post(self, request, job):
        try:
            agent.arquivos_job_delete(job)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel excluir o job: {exc}")
            return redirect("arquivos_job", job=job)
        AuditLog.objects.create(
            actor=request.user,
            action="arquivos_job_delete",
            target=job,
            ip=request.META.get("REMOTE_ADDR"),
        )
        messages.success(
            request, "Job excluido. Os arquivos de backup continuam no disco."
        )
        return redirect("arquivos_backup_index")


class ArquivosJobVerifyView(AgentPostView):
    def post(self, request, job, archive):
        try:
            resultado = agent.arquivos_job_verify(job, archive)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel verificar {archive}: {exc}")
        else:
            integro = str(resultado.get("integrity", "")).lower() == "ok"
            if integro and resultado.get("hashes_ok"):
                messages.success(
                    request,
                    f"{archive}: banco íntegro e arquivos conferem com o manifesto.",
                )
            else:
                messages.error(
                    request,
                    f"{archive}: verificacao falhou "
                    f"(integridade={resultado.get('integrity')}, "
                    f"hashes={'ok' if resultado.get('hashes_ok') else 'divergentes'}).",
                )
            AuditLog.objects.create(
                actor=request.user,
                action="arquivos_job_verify",
                target=f"{job}:{archive}",
                detail=f"integrity={resultado.get('integrity')}",
                ip=request.META.get("REMOTE_ADDR"),
            )
        return redirect("arquivos_job", job=job)


class ArquivosJobRestoreView(AgentPostView):
    def post(self, request, job, archive):
        confirmacao = (request.POST.get("confirmation") or "").strip()
        if confirmacao != archive:
            messages.error(
                request,
                "Para restaurar, digite o nome do arquivo exatamente como aparece.",
            )
            return redirect("arquivos_job", job=job)
        reiniciar = request.POST.get("restart") == "1"
        try:
            resultado = agent.arquivos_job_restore(job, archive, restart=reiniciar)
        except AgentError as exc:
            messages.error(request, f"Restauracao falhou: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="arquivos_job_restore",
                target=f"{job}:{archive}",
                detail=f"restart={resultado.get('restarted')}",
                ip=request.META.get("REMOTE_ADDR"),
            )
            aviso = (
                " O container sera reiniciado em instantes."
                if resultado.get("restarted")
                else " Reinicie o container manualmente para aplicar."
            )
            messages.success(
                request,
                f"Backup {archive} restaurado. Copia do estado anterior em "
                f"{resultado.get('security_copy')}.{aviso}",
            )
        return redirect("arquivos_job", job=job)


class ArquivosJobDownloadView(AgentView):
    def get(self, request, job, archive):
        try:
            resultado = agent.arquivos_job_download(job, archive)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel baixar {archive}: {exc}")
            return redirect("arquivos_job", job=job)
        destino = _safe_download_path(resultado.get("relative") or "")
        if destino is None or not destino.is_file():
            messages.error(request, "Arquivo de download nao encontrado no app.")
            return redirect("arquivos_job", job=job)
        AuditLog.objects.create(
            actor=request.user,
            action="arquivos_job_download",
            target=f"{job}:{archive}",
            ip=request.META.get("REMOTE_ADDR"),
        )
        return file_response(destino, resultado.get("filename") or destino.name)


class GiteaBackupView(AgentTemplateView):
    template_name = "backups/gitea.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"overview": None, "error": None, "erro_gitea": ""})
        try:
            context["overview"] = agent.gitea_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        if context.get("overview"):
            status = context["overview"].get("status") or {}
            context["erro_gitea"] = _gitea_error_text(status.get("error", ""))
        return context


class GiteaBackupStatusView(AgentView):
    def get(self, request):
        try:
            overview = agent.gitea_overview()
        except AgentError as exc:
            return JsonResponse({"error": str(exc)}, status=503)
        status = overview.get("status") or {}
        return JsonResponse(
            {
                "status": status,
                "error_label": _gitea_error_text(status.get("error", "")),
                "dumps": overview.get("dumps") or [],
                "running": bool(overview.get("running")),
            }
        )


class GiteaBackupStartView(AgentPostView):
    def post(self, request):
        alvo = (request.POST.get("target") or "host").strip()
        try:
            agent.gitea_start(alvo)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel iniciar o backup do Gitea: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="gitea_backup_start",
                target=alvo,
                ip=request.META.get("REMOTE_ADDR"),
            )
            destino = (
                "no servidor" if alvo == "host" else f"para o USB {alvo}"
            )
            messages.success(
                request,
                f"Backup do Gitea iniciado {destino}. "
                "O andamento aparece nesta página automaticamente.",
            )
        return redirect("gitea_backup")
