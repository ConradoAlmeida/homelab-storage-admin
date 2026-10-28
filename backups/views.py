from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
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


def _agenda_label(config: dict) -> str:
    if config.get("frequency") == "weekly":
        try:
            dia = WEEKDAY_LABELS[int(config.get("weekday", 0)) % 7]
        except (TypeError, ValueError):
            dia = "Segunda"
        return f"semanal ({dia.lower()}) {config.get('time', '')}"
    return f"diário {config.get('time', '')}"


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
                "credenciais": None,
                "credenciais_error": None,
            }
        )
        try:
            context["overview"] = agent.backup_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        try:
            context["credenciais"] = agent.arquivos_backup_overview()
        except AgentError as exc:
            context["credenciais_error"] = str(exc)
        if context.get("credenciais"):
            context["agenda_label"] = _agenda_label(
                context["credenciais"].get("config", {})
            )
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
                f"Backup {name} iniciado. Atualize a página para ver o status.",
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


class ArquivosBackupView(AgentTemplateView):
    template_name = "backups/arquivos.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "overview": None,
                "error": None,
                "weekdays": list(enumerate(WEEKDAY_LABELS)),
                "agenda_label": "",
            }
        )
        try:
            context["overview"] = agent.arquivos_backup_overview()
        except AgentError as exc:
            context["error"] = str(exc)
        if context.get("overview"):
            context["agenda_label"] = _agenda_label(
                context["overview"].get("config", {})
            )
        return context


class ArquivosBackupRunView(AgentPostView):
    def post(self, request):
        try:
            resultado = agent.arquivos_backup_run()
        except AgentError as exc:
            messages.error(request, f"Backup local falhou: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="arquivos_backup_run",
                target=resultado.get("archive", ""),
                detail=resultado.get("size_label", ""),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(
                request,
                f"Backup gerado: {resultado.get('archive')} "
                f"({resultado.get('size_label')}).",
            )
        return redirect("arquivos_backup_index")


class ArquivosBackupSettingsView(AgentPostView):
    def post(self, request):
        try:
            resultado = agent.arquivos_backup_settings(
                time=(request.POST.get("time") or "").strip(),
                frequency=(request.POST.get("frequency") or "daily").strip(),
                weekday=request.POST.get("weekday") or 0,
                retention_days=request.POST.get("retention_days") or 0,
            )
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel salvar o agendamento: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="credenciais_backup_settings",
                target=f"{resultado.get('frequency')} {resultado.get('time')}",
                detail=f"retencao={resultado.get('retention_days')}d",
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(
                request,
                f"Agendamento atualizado: "
                f"{'semanal' if resultado.get('frequency') == 'weekly' else 'diário'} "
                f"{resultado.get('time')}, retenção "
                f"{resultado.get('retention_days')} dias.",
            )
        return redirect("arquivos_backup_index")


class ArquivosBackupFileAddView(AgentPostView):
    def post(self, request):
        caminho = (request.POST.get("path") or "").strip()
        try:
            agent.arquivos_backup_add_file(caminho)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel incluir o arquivo: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="credenciais_backup_add_file",
                target=caminho,
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(
                request, f"{caminho} passa a entrar no proximo backup."
            )
        return redirect("arquivos_backup_index")


class ArquivosBackupFileRemoveView(AgentPostView):
    def post(self, request):
        caminho = (request.POST.get("path") or "").strip()
        try:
            agent.arquivos_backup_remove_file(caminho)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel remover o arquivo: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="credenciais_backup_remove_file",
                target=caminho,
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"{caminho} sai do proximo backup.")
        return redirect("arquivos_backup_index")


class ArquivosBackupVerifyView(AgentPostView):
    def post(self, request, archive):
        try:
            resultado = agent.arquivos_backup_verify(archive)
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
                action="arquivos_backup_verify",
                target=archive,
                detail=f"integrity={resultado.get('integrity')}",
                ip=request.META.get("REMOTE_ADDR"),
            )
        return redirect("arquivos_backup_index")


class ArquivosBackupRestoreView(AgentPostView):
    def post(self, request, archive):
        confirmacao = (request.POST.get("confirmation") or "").strip()
        if confirmacao != archive:
            messages.error(
                request,
                "Para restaurar, digite o nome do arquivo exatamente como aparece.",
            )
            return redirect("arquivos_backup_index")
        reiniciar = request.POST.get("restart") == "1"
        try:
            resultado = agent.arquivos_backup_restore(archive, restart=reiniciar)
        except AgentError as exc:
            messages.error(request, f"Restauracao falhou: {exc}")
        else:
            AuditLog.objects.create(
                actor=request.user,
                action="arquivos_backup_restore",
                target=archive,
                detail=f"restart={resultado.get('restarted')}",
                ip=request.META.get("REMOTE_ADDR"),
            )
            aviso = (
                " O container será reiniciado em instantes."
                if resultado.get("restarted")
                else " Reinicie o moya-credenciais para aplicar."
            )
            messages.success(
                request,
                f"Backup {archive} restaurado. Copia do estado anterior em "
                f"{resultado.get('security_copy')}.{aviso}",
            )
        return redirect("arquivos_backup_index")


class ArquivosBackupDownloadView(AgentView):
    def get(self, request, archive):
        try:
            resultado = agent.arquivos_backup_download(archive)
        except AgentError as exc:
            messages.error(request, f"Nao foi possivel baixar {archive}: {exc}")
            return redirect("arquivos_backup_index")
        destino = _safe_download_path(resultado.get("relative") or "")
        if destino is None or not destino.is_file():
            messages.error(request, "Arquivo de download nao encontrado no app.")
            return redirect("arquivos_backup_index")
        AuditLog.objects.create(
            actor=request.user,
            action="arquivos_backup_download",
            target=archive,
            ip=request.META.get("REMOTE_ADDR"),
        )
        return file_response(destino, resultado.get("filename") or destino.name)
