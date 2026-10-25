#!/usr/bin/env python3
"""Copia snapshots do repo restic primario para o drive frio USB."""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import shutil
import subprocess
from pathlib import Path

CONFIG = Path(os.environ.get("BACKUP_CONFIG", "/etc/homelab-backup/config.json"))
COLD_CONFIG = Path(os.environ.get("COLD_CONFIG", "/etc/homelab-backup/cold.json"))
STATUS = Path(os.environ.get("COLD_STATUS", "/etc/homelab-backup/cold-status.json"))
MOUNT = os.environ.get("COLD_MOUNT", "/mnt/coldcopy")
LOG = Path("/var/log/homelab-restic/cold-copy.log")


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def write_status(data: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATUS)


def log(text: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{now()} {text}\n")


def run(args: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def main() -> int:
    lock = open("/run/homelab-cold-copy.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("cold copy ja em execucao")
        return 0

    try:
        config = json.loads(CONFIG.read_text())
        cold = json.loads(COLD_CONFIG.read_text())
        primary = config["disks"][0]
        key = Path(cold.get("key_file") or "")
        if not key.is_file():
            raise RuntimeError("senha do restic frio ausente")
        if not os.path.ismount(MOUNT):
            proc = run(["mount", f"UUID={cold['uuid']}", MOUNT], timeout=60)
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout).strip()[:500])
        if not os.path.ismount(MOUNT):
            raise RuntimeError("drive frio nao montado")
        repo = cold.get("repo") or f"{MOUNT}/restic"
        primary_repo = primary.get("repo") or ""
        if not primary_repo:
            raise RuntimeError("repo primario ausente")
        restic = shutil.which("restic")
        if not restic:
            raise RuntimeError("restic nao instalado")
        cache = Path(MOUNT) / ".restic-cache"
        try:
            cache.mkdir(parents=True, exist_ok=True)
            os.environ["RESTIC_CACHE_DIR"] = str(cache)
        except OSError:
            pass

        started = now()
        write_status({"status": "running", "started_at": started})
        log("inicio")
        proc = run(
            [
                restic,
                "-r",
                repo,
                "--password-file",
                str(key),
                "copy",
                "--from-repo",
                primary_repo,
                "--from-password-file",
                str(key),
            ],
            timeout=21600,
        )
        log(f"copy rc={proc.returncode}\n{(proc.stderr or proc.stdout)[-3000:]}")
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout).strip()[-1500:])
        chk = run(
            [restic, "-r", repo, "--password-file", str(key), "check"],
            timeout=7200,
        )
        log(f"check rc={chk.returncode}\n{(chk.stderr or chk.stdout)[-3000:]}")
        if chk.returncode != 0:
            raise RuntimeError("copia ok, mas restic check falhou: " + (chk.stderr or chk.stdout).strip()[-1000:])
        raw = run(
            [restic, "-r", repo, "--password-file", str(key), "snapshots", "--json"],
            timeout=120,
        )
        snapshots = len(json.loads(raw.stdout)) if raw.returncode == 0 else 0
        write_status(
            {
                "status": "success",
                "started_at": started,
                "finished_at": now(),
                "snapshots": snapshots,
                "message": "restic copy + check OK",
            }
        )
        log(f"fim success snapshots={snapshots}")
        return 0
    except Exception as exc:
        write_status(
            {
                "status": "failed",
                "finished_at": now(),
                "message": str(exc)[:2000],
            }
        )
        log(f"erro: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
