from __future__ import annotations

import datetime as dt
import mimetypes
import os
import re
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from core.agent import AgentError, agent

SNAP_RE = re.compile(r"^@GMT-\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}$")


def _share(share: str) -> dict:
    try:
        for item in agent.list_shares(include_size=False):
            if item["name"] == share:
                return item
    except AgentError as exc:
        raise Http404(f"Agente indisponivel: {exc}") from exc
    raise Http404("Share nao encontrado")


def _snapdir(share: str) -> Path:
    info = _share(share)
    snapdir = info.get("snapdir")
    if snapdir:
        return Path(snapdir)
    # Compatibilidade com agentes antigos que ainda nao devolvem snapdir.
    return Path(settings.SNAPSHOT_ROOT) / share


def _snapshots(share: str) -> list[dict]:
    root = _snapdir(share)
    if not root.is_dir():
        return []
    result = []
    for entry in root.iterdir():
        if not entry.is_dir() or not SNAP_RE.match(entry.name):
            continue
        try:
            stamp = dt.datetime.strptime(entry.name, "@GMT-%Y.%m.%d-%H.%M.%S")
            label = stamp.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            label = entry.name
        result.append({"name": entry.name, "label": label})
    return sorted(result, key=lambda item: item["name"], reverse=True)


def _base(share: str, snapshot: str) -> Path:
    info = _share(share)
    if snapshot == "live":
        return Path(info["path"])
    if not SNAP_RE.match(snapshot):
        raise Http404("Snapshot invalido")
    snapdir = info.get("snapdir")
    if not snapdir:
        raise Http404("Share sem snapshots")
    return Path(snapdir) / snapshot


def _safe_target(base: Path, rel: str) -> Path:
    rel = (rel or "").strip("/")
    if ".." in PurePosixPath(rel).parts:
        raise Http404("Caminho invalido")
    base_res = base.resolve()
    target = (base_res / rel).resolve()
    if target != base_res and base_res not in target.parents:
        raise Http404("Caminho fora do share")
    return target


def _url_browse(share: str, snapshot: str, path: str = "") -> str:
    if path:
        return reverse("history_browse", args=[share, snapshot, path])
    return reverse("history_browse_root", args=[share, snapshot])


def _breadcrumbs(share: str, snapshot: str, path: str) -> list[dict]:
    crumbs = [{"name": share, "url": _url_browse(share, snapshot)}]
    parts = []
    for part in path.split("/"):
        if not part:
            continue
        parts.append(part)
        crumbs.append(
            {"name": part, "url": _url_browse(share, snapshot, "/".join(parts))}
        )
    return crumbs


@login_required
def index(request):
    context = {"agent_error": None, "shares": []}
    try:
        shares = agent.list_shares(include_size=False)
    except AgentError as exc:
        context["agent_error"] = str(exc)
        return render(request, "history/index.html", context)

    for item in shares:
        snaps = _snapshots(item["name"])
        item["snapshots"] = snaps
        item["snapshot_count"] = len(snaps)
        item["last_snapshot"] = snaps[0]["label"] if snaps else None
        item["url"] = reverse("history_share", args=[item["name"]])
    context["shares"] = shares
    return render(request, "history/index.html", context)


@login_required
def share_detail(request, share: str):
    _share(share)
    return redirect("history_browse_root", share=share, snapshot="live")


@login_required
def browse(request, share: str, snapshot: str, filepath: str = ""):
    info = _share(share)
    base = _base(share, snapshot)
    target = _safe_target(base, filepath)
    if target.is_file():
        return redirect("history_versions", share=share, filepath=filepath)
    if not target.is_dir():
        raise Http404("Diretorio nao encontrado")

    entries = []
    with os.scandir(target) as iterator:
        for entry in iterator:
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            is_dir = entry.is_dir(follow_symlinks=False)
            rel = f"{filepath.strip('/')}/{entry.name}".strip("/")
            entries.append(
                {
                    "name": entry.name,
                    "is_dir": is_dir,
                    "size": 0 if is_dir else stat.st_size,
                    "mtime": dt.datetime.fromtimestamp(stat.st_mtime),
                    "url": _url_browse(share, snapshot, rel)
                    if is_dir
                    else reverse("history_download", args=[share, snapshot, rel]),
                    "versions_url": None
                    if is_dir
                    else reverse("history_versions", args=[share, rel]),
                }
            )
    entries.sort(key=lambda item: (not item["is_dir"], item["name"].casefold()))

    paginator = Paginator(entries, 100)
    page_obj = paginator.get_page(request.GET.get("page"))
    snapshots = _snapshots(share)
    snapdir = info.get("snapdir")
    for snap in snapshots:
        candidate = Path(snapdir) / snap["name"] / filepath if snapdir else None
        same_path = bool(filepath) and candidate is not None and candidate.exists()
        snap["url"] = _url_browse(share, snap["name"], filepath if same_path else "")

    parts = [part for part in filepath.split("/") if part]
    parent_url = (
        _url_browse(share, snapshot, "/".join(parts[:-1])) if parts else None
    )
    live_candidate = Path(info["path"]) / filepath
    live_url = (
        _url_browse(share, "live", filepath)
        if (not filepath or live_candidate.exists())
        else _url_browse(share, "live")
    )
    context = {
        "share": info,
        "snapshot": snapshot,
        "is_snapshot": snapshot != "live",
        "path": filepath,
        "parent_url": parent_url,
        "crumbs": _breadcrumbs(share, snapshot, filepath),
        "entries": page_obj.object_list,
        "page_obj": page_obj,
        "snapshots": snapshots,
        "live_url": live_url,
        "current_url": _url_browse(share, snapshot),
        "share_url": reverse("history_share", args=[share]),
    }
    return render(request, "history/browse.html", context)


@login_required
def download(request, share: str, snapshot: str, filepath: str):
    _share(share)
    base = _base(share, snapshot)
    target = _safe_target(base, filepath)
    if not target.is_file():
        raise Http404("Arquivo nao encontrado")
    content_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        open(target, "rb"),
        as_attachment=True,
        filename=target.name,
        content_type=content_type or "application/octet-stream",
    )


@login_required
def versions(request, share: str, filepath: str):
    info = _share(share)
    live_base = Path(info["path"])
    live_target = _safe_target(live_base, filepath)

    result = []
    snapdir = info.get("snapdir")
    for snap in _snapshots(share):
        snap_base = Path(snapdir) / snap["name"] if snapdir else None
        if snap_base is None:
            continue
        try:
            candidate = _safe_target(snap_base, filepath)
        except Http404:
            continue
        if not candidate.is_file():
            continue
        stat = candidate.stat()
        result.append(
            {
                "name": snap["name"],
                "label": snap["label"],
                "size": stat.st_size,
                "mtime": dt.datetime.fromtimestamp(stat.st_mtime),
                "url": reverse("history_download", args=[share, snap["name"], filepath]),
            }
        )

    live_stat = live_target.stat() if live_target.is_file() else None
    if not result and live_stat is None:
        raise Http404("Arquivo nao encontrado")
    context = {
        "share": info,
        "filepath": filepath,
        "filename": Path(filepath).name,
        "versions": result,
        "live": {
            "size": live_stat.st_size,
            "mtime": dt.datetime.fromtimestamp(live_stat.st_mtime),
            "url": reverse("history_download", args=[share, "live", filepath]),
        }
        if live_stat
        else None,
        "share_url": reverse("history_share", args=[share]),
        "browse_url": _url_browse(share, "live", str(PurePosixPath(filepath).parent))
        if str(PurePosixPath(filepath).parent) != "."
        else _url_browse(share, "live"),
    }
    return render(request, "history/versions.html", context)
