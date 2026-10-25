#!/usr/bin/env python3
"""Executa um job de backup restic configurado pelo app.

Uso: homelab-restic-backup <job>
Roda como root via homelab-restic-backup@<job>.service.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG = Path(os.environ.get("BACKUP_CONFIG", "/etc/homelab-backup/config.json"))
STATUS_DIR = Path(os.environ.get("BACKUP_STATUS_DIR", "/etc/homelab-backup/status"))
LOG_DIR = Path(os.environ.get("BACKUP_LOG_DIR", "/var/log/homelab-restic"))
JOB_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def write_status(name: str, data: dict) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATUS_DIR, 0o700)
    path = STATUS_DIR / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def log(name: str, text: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / f"{name}.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{now()} {text}\n")


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def tail(proc: subprocess.CompletedProcess) -> str:
    return ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-2500:]


def main() -> int:
    if len(sys.argv) != 2 or not JOB_RE.match(sys.argv[1]):
        print("uso: homelab-restic-backup <job>")
        return 2
    name = sys.argv[1]

    try:
        config = json.loads(CONFIG.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"configuracao invalida: {exc}")
        return 2
    job = next((item for item in config.get("jobs", []) if item.get("name") == name), None)
    if job is None:
        print(f"job nao encontrado: {name}")
        return 2
    disk = next(
        (
            item
            for item in config.get("disks", [])
            if item.get("uuid") == job.get("disk_uuid")
        ),
        None,
    )
    if disk is None:
        write_status(
            name,
            {"job": name, "status": "failed", "finished_at": now(), "message": "disco nao encontrado"},
        )
        return 1

    mountpoint = Path(disk.get("mountpoint") or "")
    repo = disk.get("repo") or ""
    key_file = Path(disk.get("key_file") or "")
    if not os.path.ismount(mountpoint):
        write_status(
            name,
            {"job": name, "status": "failed", "finished_at": now(), "message": "disco de backup nao montado"},
        )
        return 1
    if not repo or not key_file.is_file():
        write_status(
            name,
            {"job": name, "status": "failed", "finished_at": now(), "message": "repo/senha restic ausente"},
        )
        return 1
    restic = shutil.which("restic")
    if not restic:
        write_status(
            name,
            {"job": name, "status": "failed", "finished_at": now(), "message": "restic nao instalado"},
        )
        return 1
    try:
        cache_dir = Path(disk["mountpoint"]) / ".restic-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["RESTIC_CACHE_DIR"] = str(cache_dir)
    except OSError:
        pass

    source_paths = [str(item) for item in job.get("source_paths", []) if item]
    if not source_paths:
        write_status(
            name,
            {"job": name, "status": "failed", "finished_at": now(), "message": "nenhuma fonte configurada"},
        )
        return 1
    missing = [item for item in source_paths if not os.path.isdir(item)]
    if missing:
        write_status(
            name,
            {"job": name, "status": "failed", "finished_at": now(), "message": "fonte ausente: " + ", ".join(missing)},
        )
        return 1

    lock_path = Path(f"/run/homelab-restic-{name}.lock")
    lock_file = lock_path.open("w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log(name, "job ja esta em execucao; saindo")
        return 0

    started = now()
    write_status(name, {"job": name, "status": "running", "started_at": started})
    log(name, "inicio")

    args = [
        restic,
        "-r",
        repo,
        "--password-file",
        str(key_file),
        "backup",
        "--tag",
        "homelab",
        *source_paths,
    ]
    for pattern in job.get("excludes", []):
        if pattern:
            args.extend(["--exclude", str(pattern)])

    proc = run(args)
    log(name, f"backup rc={proc.returncode}\n{tail(proc)}")
    if proc.returncode != 0:
        write_status(
            name,
            {
                "job": name,
                "status": "failed",
                "started_at": started,
                "finished_at": now(),
                "exit_code": proc.returncode,
                "message": tail(proc),
            },
        )
        return 1

    snapshot = ""
    match = re.search(r"snapshot ([0-9a-f]+) saved", proc.stdout or "")
    if match:
        snapshot = match.group(1)

    retention = job.get("retention") or {}
    forget = [restic, "-r", repo, "--password-file", str(key_file), "forget"]
    has_retention = False
    for key, flag in (
        ("daily", "--keep-daily"),
        ("weekly", "--keep-weekly"),
        ("monthly", "--keep-monthly"),
    ):
        try:
            count = int(retention.get(key) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            forget.extend([flag, str(count)])
            has_retention = True
    if has_retention:
        forget.append("--prune")
        fproc = run(forget)
        log(name, f"forget rc={fproc.returncode}\n{tail(fproc)}")
        if fproc.returncode != 0:
            write_status(
                name,
                {
                    "job": name,
                    "status": "warning",
                    "started_at": started,
                    "finished_at": now(),
                    "snapshot_id": snapshot,
                    "message": "backup ok; forget/prune falhou: " + tail(fproc),
                },
            )
            return 0

    write_status(
        name,
        {
            "job": name,
            "status": "success",
            "started_at": started,
            "finished_at": now(),
            "snapshot_id": snapshot,
            "message": tail(proc),
        },
    )
    log(name, "fim success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
