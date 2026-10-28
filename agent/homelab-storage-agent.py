#!/usr/bin/env python3
"""Agente privilegiado do Homelab Storage Admin.

Roda como root no host e expoe um Unix socket com operacoes validadas de
Samba, usuarios e snapshots. O app Django nunca executa shell direto.
"""
from __future__ import annotations

import configparser
import datetime as dt
import grp
import hashlib
import json
import os
import pwd
import re
import secrets
import shutil
import socketserver
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from pathlib import Path, PurePosixPath

SOCKET_PATH = os.environ.get(
    "AGENT_SOCKET",
    os.environ.get("SOCKET_PATH", "/run/homelab-storage-admin/agent.sock"),
)
SMB_CONF = os.environ.get("SMB_CONF", "/etc/samba/smb.conf")
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/etc/homelab-storage-agent")
SNAP_CONFIG = os.environ.get("SNAP_CONFIG", f"{CONFIG_DIR}/snapshots.json")
BACKUP_CONFIG = os.environ.get("BACKUP_CONFIG", "/etc/homelab-backup/config.json")
BACKUP_SECRETS = os.environ.get("BACKUP_SECRETS", "/etc/homelab-backup/secrets")
BACKUP_STATUS_DIR = os.environ.get("BACKUP_STATUS_DIR", "/etc/homelab-backup/status")
BACKUP_ROOT = os.environ.get("BACKUP_ROOT", "/mnt/backup")
COLD_CONFIG = os.environ.get("COLD_CONFIG", "/etc/homelab-backup/cold.json")
COLD_STATUS = os.environ.get("COLD_STATUS", "/etc/homelab-backup/cold-status.json")
COLD_MOUNT = os.environ.get("COLD_MOUNT", "/mnt/coldcopy")
CREDENCIAIS_CONFIG = os.environ.get(
    "CREDENCIAIS_CONFIG", "/etc/homelab-backup/credenciais.json"
)
CREDENCIAIS_STATUS = os.environ.get(
    "CREDENCIAIS_STATUS", "/etc/homelab-backup/credenciais-status.json"
)
CREDENCIAIS_BACKUP_DIR = os.environ.get(
    "CREDENCIAIS_BACKUP_DIR", "/var/backups/moya-credenciais"
)
CREDENCIAIS_DB = os.environ.get(
    "CREDENCIAIS_DB", "/home/conrado/moya_credenciais_app/data/db.sqlite3"
)
CREDENCIAIS_ENV = os.environ.get(
    "CREDENCIAIS_ENV", "/home/conrado/moya_credenciais_app/.env"
)
CREDENCIAIS_CONTAINER = os.environ.get("CREDENCIAIS_CONTAINER", "moya-credenciais")
CREDENCIAIS_TIME = os.environ.get("CREDENCIAIS_TIME", "03:30")
CREDENCIAIS_RETENTION_DAYS = int(os.environ.get("CREDENCIAIS_RETENTION_DAYS", "30"))
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/homelab-storage-agent.log")
DATA_DIR = os.environ.get("DATA_DIR", "/var/lib/homelab-storage-admin")
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", os.path.join(DATA_DIR, "downloads"))
STORAGE_CACHE = os.environ.get(
    "STORAGE_CACHE", "/var/lib/homelab-storage-admin/storage-cache.json"
)
STORAGE_CACHE_MAX_AGE = int(os.environ.get("STORAGE_CACHE_MAX_AGE", "86400"))

USER_RE = re.compile(r"^[a-z][a-z0-9._-]{2,31}$")
SHARE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
GROUP_RE = re.compile(r"^[a-z][a-z0-9._-]{1,31}$")
SNAP_RE = re.compile(r"^@GMT-\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}$")
RESTIC_SNAPSHOT_RE = re.compile(r"^[0-9a-fA-F]{8,64}$")
BACKUP_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
COLD_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{16,64}$")
JOB_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
CREDENCIAIS_ARCHIVE_RE = re.compile(r"^moya-credenciais-\d{8}-\d{6}\.tar\.gz$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

ALLOWED_PATH_PREFIXES = tuple(
    p.strip().rstrip("/") + "/"
    for p in os.environ.get("ALLOWED_PATH_PREFIXES", "/mnt/nas/").split(",")
    if p.strip()
)
DF_MOUNTS = tuple(
    m.strip() for m in os.environ.get("DF_MOUNTS", "/,/mnt/nas").split(",") if m.strip()
)
STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "/mnt/nas")
SNAPSHOT_ROOT = os.environ.get("SNAPSHOT_ROOT", "/mnt/nas/.snapshots")
SHARE_OWNER = os.environ.get("SHARE_OWNER", "conrado")
SNAPSHOT_BACKEND = os.environ.get("SNAPSHOT_BACKEND", "auto").strip().lower()
DENY_SNAPSHOT = {
    s.strip() for s in os.environ.get("SNAPSHOT_DENYLIST", "").split(",") if s.strip()
}
RESERVED_SHARES = {"global", "homes", "printers", "print$"}
RESERVED_GROUPS = {
    "root",
    "sudo",
    "adm",
    "wheel",
    "users",
    "nogroup",
    "nobody",
    "systemd-journal",
    "docker",
}
BLOCK_DEVICE_RE = re.compile(
    r"^/dev/(?:sd[a-z]+|nvme\d+n\d+|mmcblk\d+|vd[a-z]+|xvd[a-z]+)$"
)

# A politica e criada pelo app; o agente so mantem o estado em disco.
DEFAULT_POLICY: dict = {}


class AgentError(Exception):
    pass


def log(message: str) -> None:
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {message}\n")
    except OSError:
        pass


def run(args: list[str], input_text: str | None = None, timeout: int = 60) -> str:
    try:
        proc = subprocess.run(
            args,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AgentError(f"Comando nao encontrado: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AgentError(f"Tempo esgotado executando {args[0]}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise AgentError(f"{args[0]} falhou: {detail}")
    return proc.stdout


def run_optional(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """Executa sem levantar erro; usado para consultas de estado/SMART."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, "", f"timeout: {exc}"


def _existing_parent(path: str) -> str:
    """Retorna o diretorio existente mais proximo (para detectar fstype)."""
    current = Path(path or "/")
    while not current.exists() and current != current.parent:
        current = current.parent
    return str(current)


def _fstype(path: str) -> str | None:
    target = _existing_parent(path)
    rc, out, _ = run_optional(
        ["findmnt", "-n", "-o", "FSTYPE", "--target", target], timeout=5
    )
    if rc == 0:
        value = out.strip().splitlines()
        if value:
            return value[0].strip()
    # fallback para ambientes sem findmnt (inclusive testes/containers)
    rc, out, _ = run_optional(["stat", "-f", "-c", "%T", target], timeout=5)
    if rc == 0 and out.strip():
        return out.strip().splitlines()[0].strip()
    return None


def snapshot_backend_for(path: str, configured: str | None = None) -> str:
    """Resolve o backend de snapshot para um caminho.

    ``auto`` escolhe btrfs quando o filesystem e Btrfs e rsync nos demais.
    """
    mode = (configured or SNAPSHOT_BACKEND or "auto").strip().lower()
    if mode == "none":
        return "none"
    if mode == "rsync":
        return "rsync"
    if mode == "btrfs":
        return "btrfs" if _fstype(path) == "btrfs" else "none"
    if mode != "auto":
        raise AgentError(f"SNAPSHOT_BACKEND invalido: {mode}")
    return "btrfs" if _fstype(path) == "btrfs" else "rsync"


def snapshot_dir_for(share: str, path: str, backend: str) -> str:
    if backend == "btrfs":
        return os.path.join(SNAPSHOT_ROOT, share)
    if backend == "rsync":
        return os.path.join(path, ".snapshots")
    return ""


def detect_hwmon_fans(base: str = "/sys/class/hwmon") -> bool:
    for hw in Path(base).glob("hwmon*"):
        if (hw / "fan1_input").exists() or (hw / "pwm1").exists():
            return True
    return False


def host_capabilities() -> dict:
    fstype = _fstype(STORAGE_ROOT)
    return {
        "btrfs": bool(shutil.which("btrfs")),
        "restic": bool(shutil.which("restic")),
        "smartctl": bool(shutil.which("smartctl")),
        "hdparm": bool(shutil.which("hdparm")),
        "mdadm": bool(shutil.which("mdadm")),
        "hwmon_fans": detect_hwmon_fans(),
        "storage_root_mounted": os.path.ismount(STORAGE_ROOT),
        "storage_root_fstype": fstype,
        "snapshot_backend": snapshot_backend_for(STORAGE_ROOT),
        "credenciais_backup": bool(
            Path(CREDENCIAIS_DB).is_file() and Path(CREDENCIAIS_ENV).is_file()
        ),
    }


def _disk_state(device: str) -> str:
    if not device.startswith("/dev/sd"):
        return "active"
    rc, out, _ = run_optional(["hdparm", "-C", device], timeout=5)
    if rc == 0:
        match = re.search(r"drive state is:\s*(\S+)", out)
        if match:
            return match.group(1)
    return "unknown"


def _smart_summary(device: str) -> dict:
    rc, out, err = run_optional(
        ["smartctl", "-n", "standby", "-H", "-A", "-j", device], timeout=15
    )
    if rc == 2:
        return {"state": "standby", "skipped": True}
    if rc != 0:
        return {"state": "unavailable", "error": (err or out).strip()[:300]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"state": "unavailable", "error": "resposta smartctl invalida"}

    attributes = {}
    for item in data.get("ata_smart_attributes", {}).get("table", []):
        attributes[str(item.get("id"))] = {
            "name": item.get("name"),
            "value": item.get("value"),
            "worst": item.get("worst"),
            "thresh": item.get("thresh"),
            "raw": (item.get("raw") or {}).get("value"),
        }

    passed = (data.get("smart_status") or {}).get("passed")
    if "passed" in (data.get("smart_status") or {}):
        health = "PASSED" if passed else "FAILED"
    else:
        health = "UNKNOWN"
    return {
        "state": "active",
        "model": data.get("model_name"),
        "serial": data.get("serial_number"),
        "temperature": (data.get("temperature") or {}).get("current"),
        "health": health,
        "power_on_hours": (data.get("power_on_time") or {}).get("hours"),
        "attributes": attributes,
    }


def _collect_mounts(device: dict) -> list[str]:
    mounts = [m for m in (device.get("mountpoints") or []) if m]
    for child in device.get("children") or []:
        mounts.extend(_collect_mounts(child))
    return mounts


def _system_info() -> dict:
    zones = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            kind = (zone / "type").read_text().strip()
            temp = int((zone / "temp").read_text().strip()) / 1000
        except (OSError, ValueError):
            continue
        zones.append({"type": kind, "temp": temp})

    fans = []
    for hw in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        name = ""
        try:
            name = (hw / "name").read_text().strip()
        except OSError:
            pass
        fan = None
        pwm = None
        try:
            fan = int((hw / "fan1_input").read_text().strip())
        except (OSError, ValueError):
            pass
        try:
            pwm = int((hw / "pwm1").read_text().strip())
        except (OSError, ValueError):
            pass
        if fan is not None or pwm is not None:
            fans.append(
                {
                    "name": name,
                    "rpm": fan,
                    "pwm": pwm,
                    "pwm_percent": round(pwm / 255 * 100) if pwm is not None else None,
                }
            )

    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                mem[key] = int(value.strip().split()[0])
    except (OSError, ValueError):
        pass

    load = os.getloadavg()
    cpu_percent = None
    try:
        def cpu_sample() -> tuple[int, int]:
            fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
            values = [int(value) for value in fields]
            total = sum(values)
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return total, idle

        total1, idle1 = cpu_sample()
        time.sleep(0.2)
        total2, idle2 = cpu_sample()
        delta_total = total2 - total1
        delta_idle = idle2 - idle1
        if delta_total > 0:
            cpu_percent = round(100 * (delta_total - delta_idle) / delta_total, 1)
    except (OSError, ValueError, IndexError):
        pass
    return {
        "zones": zones,
        "fans": fans,
        "load": {"l1": load[0], "l5": load[1], "l15": load[2]},
        "cpu_percent": cpu_percent,
        "mem_total_kb": mem.get("MemTotal"),
        "mem_available_kb": mem.get("MemAvailable"),
        "mem_total_mb": round(mem["MemTotal"] / 1024) if "MemTotal" in mem else None,
        "mem_available_mb": round(mem["MemAvailable"] / 1024)
        if "MemAvailable" in mem
        else None,
    }


def _md_names(mdstat: str) -> list[str]:
    return re.findall(r"^(md\d+)\s*:", mdstat or "", flags=re.MULTILINE)


def _md_details(mdstat: str) -> str:
    details = []
    for name in _md_names(mdstat):
        rc, out, _ = run_optional(["mdadm", "--detail", f"/dev/{name}"], timeout=10)
        if rc == 0 and out.strip():
            details.append(out.strip())
    return "\n\n".join(details)


def _collect_storage_overview() -> dict:
    raw = run(
        ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL,TRAN"]
    )
    data = json.loads(raw)
    disks = []
    for device in data.get("blockdevices", []):
        name = device.get("name", "")
        if device.get("type") != "disk" or name.startswith("loop"):
            continue
        path = f"/dev/{name}"
        state = _disk_state(path)
        smart_capable = name.startswith(("sd", "nvme", "vd", "xvd", "mmcblk"))
        smart = _smart_summary(path) if smart_capable else {"state": "unavailable"}
        disks.append(
            {
                "name": name,
                "path": path,
                "size": device.get("size"),
                "model": (device.get("model") or "").strip(),
                "serial": (device.get("serial") or "").strip(),
                "tran": device.get("tran"),
                "fstype": device.get("fstype"),
                "mounts": _collect_mounts(device),
                "state": state,
                "smart": smart,
            }
        )

    raid = {}
    try:
        raid["mdstat"] = Path("/proc/mdstat").read_text()
    except OSError:
        raid["mdstat"] = ""
    raid["detail"] = _md_details(raid["mdstat"])

    btrfs = {}
    if shutil.which("btrfs"):
        rc, out, _ = run_optional(
            ["btrfs", "filesystem", "usage", "--raw", STORAGE_ROOT], timeout=15
        )
        btrfs["usage"] = out if rc == 0 else ""
        rc, out, _ = run_optional(
            ["btrfs", "device", "stats", STORAGE_ROOT], timeout=15
        )
        btrfs["stats"] = out if rc == 0 else ""
        rc, out, _ = run_optional(
            ["btrfs", "scrub", "status", "-d", STORAGE_ROOT], timeout=15
        )
        btrfs["scrub"] = out if rc == 0 else ""

    return {
        "system": _system_info(),
        "disks": disks,
        "raid": raid,
        "btrfs": btrfs,
    }


def _load_storage_cache() -> dict | None:
    path = Path(STORAGE_CACHE)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _save_storage_cache(data: dict) -> None:
    path = Path(STORAGE_CACHE)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _refresh_storage_cache() -> dict:
    data = _collect_storage_overview()
    data["collected_at"] = dt.datetime.now().isoformat(timespec="seconds")
    data["collected_ts"] = time.time()
    data["cache_age_seconds"] = 0
    data["stale"] = False
    _save_storage_cache(data)
    return data


def op_storage_overview(force=False, **_):
    if force:
        return _refresh_storage_cache()
    data = _load_storage_cache()
    if data is None:
        return _refresh_storage_cache()
    age = max(0, int(time.time() - float(data.get("collected_ts") or 0)))
    data["cache_age_seconds"] = age
    data["stale"] = age > STORAGE_CACHE_MAX_AGE
    return data


def op_live_metrics(**_):
    """Metricas leves do hardware do Pi; nao toca em discos/SMART."""
    return {
        "system": _system_info(),
        "collected_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def op_refresh_storage(**_):
    return _refresh_storage_cache()


def op_storage_smart(device: str, **_):
    if not BLOCK_DEVICE_RE.match(device or ""):
        raise AgentError("Dispositivo invalido")
    if not os.path.exists(device):
        raise AgentError(f"Dispositivo nao encontrado: {device}")
    state = _disk_state(device)
    if state in ("standby", "sleeping"):
        return {
            "device": device,
            "state": state,
            "skipped": True,
            "message": "Disco em standby; nao vou acordar para ler SMART",
        }
    data = _smart_summary(device)
    data["device"] = device
    data["state"] = state
    return data


def op_storage_smart_test(device: str, kind: str = "short", **_):
    if not BLOCK_DEVICE_RE.match(device or ""):
        raise AgentError("Dispositivo invalido")
    if kind not in ("short", "long"):
        raise AgentError("Tipo de teste invalido (short/long)")
    if not os.path.exists(device):
        raise AgentError(f"Dispositivo nao encontrado: {device}")
    state = _disk_state(device)
    if state in ("standby", "sleeping"):
        raise AgentError("Disco em standby; nao vou acordar para iniciar teste SMART")
    rc, out, err = run_optional(["smartctl", "-t", kind, device], timeout=30)
    if rc != 0:
        raise AgentError((err or out).strip()[:500] or "smartctl falhou")
    return {"device": device, "kind": kind, "started": True, "output": out.strip()}


def validate_user(username: str) -> str:
    if not USER_RE.match(username or ""):
        raise AgentError("Usuario invalido (use minusculas, 3-32: a-z 0-9 . _ -)")
    return username


def validate_group(group: str) -> str:
    if not GROUP_RE.match(group or ""):
        raise AgentError(f"Grupo invalido: {group!r}")
    if not getent_group(group):
        raise AgentError(f"Grupo nao existe: {group}")
    return group


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise AgentError("A senha precisa ter no minimo 8 caracteres")
    if len(password) > 256:
        raise AgentError("Senha muito longa")
    if "\n" in password or "\r" in password:
        raise AgentError("Senha nao pode conter quebra de linha")
    return password


def getent_group(name: str) -> bool:
    try:
        grp.getgrnam(name)
        return True
    except KeyError:
        return False


def system_groups() -> dict[str, int]:
    groups = {}
    for entry in grp.getgrall():
        groups[entry.gr_name] = entry.gr_gid
    return groups


def managed_groups() -> set[str]:
    """Grupos gerenciados pelo app (GID >= 1000). Preserva sudo/adm etc."""
    return {name for name, gid in system_groups().items() if gid >= 1000}


def user_groups(username: str) -> list[str]:
    try:
        return sorted(set(os.getgrouplist(username, pwd.getpwnam(username).pw_gid)))
    except KeyError:
        return []


def group_names_for(username: str) -> list[str]:
    names = []
    for name, gid in system_groups().items():
        if gid in user_groups(username):
            names.append(name)
    return sorted(names)


def samba_enabled(username: str) -> bool:
    try:
        out = run(["pdbedit", "-Lv", "-u", username])
    except AgentError:
        return False
    for line in out.splitlines():
        if line.strip().startswith("Account Flags:"):
            flags = line.split(":", 1)[1]
            return "D" not in flags
    return True


# ----------------------------- operacoes ---------------------------------


def op_ping(**_):
    return {
        "pong": True,
        "agent": "homelab-storage-agent",
        "capabilities": host_capabilities(),
    }


def op_host_capabilities(**_):
    return host_capabilities()


def op_df(**_):
    mounts = list(DF_MOUNTS)
    backup_root = Path(BACKUP_ROOT)
    if backup_root.is_dir():
        for path in sorted(backup_root.iterdir()):
            if path.is_dir() and os.path.ismount(path):
                mounts.append(str(path))
    volumes = []
    for mount in dict.fromkeys(mounts):
        if not os.path.ismount(mount) and mount != "/":
            continue
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        percent = round(usage.used / usage.total * 100, 1) if usage.total else 0
        volumes.append(
            {
                "mount": mount,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": percent,
            }
        )
    return {"volumes": volumes}


def op_list_groups(**_):
    return sorted(name for name, gid in system_groups().items() if gid >= 1000)


def op_create_group(name: str, gid: int | None = None, **_):
    if not GROUP_RE.match(name or ""):
        raise AgentError("Grupo invalido (minusculas, 2-32: a-z 0-9 . _ -)")
    if name in RESERVED_GROUPS:
        raise AgentError(f"Nome de grupo reservado: {name}")
    if getent_group(name):
        raise AgentError(f"Grupo ja existe: {name}")

    command = ["groupadd"]
    if gid is not None:
        try:
            gid = int(gid)
        except (TypeError, ValueError) as exc:
            raise AgentError("GID invalido") from exc
        if gid < 1000 or gid > 60000:
            raise AgentError("GID deve estar entre 1000 e 60000")
        try:
            grp.getgrgid(gid)
            raise AgentError(f"GID ja em uso: {gid}")
        except KeyError:
            pass
        command.extend(["-g", str(gid)])
    command.append(name)

    run(command)
    log(f"CREATE_GROUP {name} gid={gid or 'auto'}")
    return {"name": name, "gid": gid}


def op_list_users(**_):
    try:
        raw = run(["pdbedit", "-L"])
    except AgentError:
        return []
    users = []
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 2:
            continue
        username = parts[0].strip()
        if not username:
            continue
        fullname = parts[2].strip() if len(parts) > 2 else ""
        try:
            pwd.getpwnam(username)
        except KeyError:
            continue
        users.append(
            {
                "username": username,
                "uid": parts[1].strip(),
                "fullname": fullname,
                "groups": group_names_for(username),
                "enabled": samba_enabled(username),
            }
        )
    return sorted(users, key=lambda item: item["username"])


def op_create_user(username: str, password: str, groups=None, **_):
    validate_user(username)
    validate_password(password)
    try:
        pwd.getpwnam(username)
        raise AgentError(f"Usuario ja existe: {username}")
    except KeyError:
        pass
    groups = [validate_group(g) for g in (groups or [])]

    run(["useradd", "-m", "-s", "/usr/sbin/nologin", username])
    try:
        run(["smbpasswd", "-s", "-a", username], input_text=f"{password}\n{password}\n")
        if groups:
            run(["usermod", "-aG", ",".join(groups), username])
    except AgentError:
        run(["userdel", "-r", username]) if _user_exists(username) else None
        raise
    log(f"CREATE_USER {username} groups={','.join(groups)}")
    return {"username": username, "groups": groups}


def _user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def op_set_password(username: str, password: str, **_):
    validate_user(username)
    validate_password(password)
    if not _user_exists(username):
        raise AgentError(f"Usuario nao existe: {username}")
    run(["smbpasswd", "-s", username], input_text=f"{password}\n{password}\n")
    log(f"SET_PASSWORD {username}")
    return {"username": username}


def op_set_groups(username: str, groups=None, **_):
    validate_user(username)
    if not _user_exists(username):
        raise AgentError(f"Usuario nao existe: {username}")
    requested = {validate_group(g) for g in (groups or [])}
    current = set(group_names_for(username))
    keep = current - managed_groups()  # preserva sudo/adm/etc
    final = sorted(keep | requested)
    run(["usermod", "-G", ",".join(final), username] if final else ["usermod", "-G", "", username])
    log(f"SET_GROUPS {username} groups={','.join(final)}")
    return {"username": username, "groups": final}


def op_toggle_user(username: str, enabled: bool, **_):
    validate_user(username)
    if not _user_exists(username):
        raise AgentError(f"Usuario nao existe: {username}")
    if enabled:
        run(["smbpasswd", "-e", username])
        run(["usermod", "-U", username])
    else:
        run(["smbpasswd", "-d", username])
        run(["usermod", "-L", username])
    log(f"TOGGLE_USER {username} enabled={enabled}")
    return {"username": username, "enabled": enabled}


PROTECTED_USERS = {"root", "admin", "conrado"}


def op_delete_user(username: str, **_):
    validate_user(username)
    if username in PROTECTED_USERS or username == SHARE_OWNER:
        raise AgentError(f"Usuario protegido: {username}")
    try:
        entry = pwd.getpwnam(username)
    except KeyError as exc:
        raise AgentError(f"Usuario nao existe: {username}") from exc
    if entry.pw_uid < 1000:
        raise AgentError(f"Usuario protegido: {username}")
    if set(group_names_for(username)) & {"sudo", "adm", "wheel", "root"}:
        raise AgentError(f"Usuario protegido: {username}")
    subprocess.run(["smbpasswd", "-x", username], check=False)
    run(["userdel", "-r", username])
    log(f"DELETE_USER {username}")
    return {"username": username}


def op_delete_group(name: str, **_):
    if name in RESERVED_GROUPS:
        raise AgentError(f"Grupo protegido: {name}")
    validate_group(name)
    entry = grp.getgrnam(name)
    if entry.gr_gid < 1000:
        raise AgentError(f"Grupo protegido: {name}")
    donos = [user.pw_name for user in pwd.getpwall() if user.pw_gid == entry.gr_gid]
    if donos:
        raise AgentError(
            f"Grupo {name} e o grupo primario de {', '.join(donos)}. Exclua o usuario."
        )
    run(["groupdel", name])
    log(f"DELETE_GROUP {name}")
    return {"name": name}


def _parse_smb_conf() -> configparser.ConfigParser:
    text = run(["testparm", "-s"])
    lines = text.splitlines()
    # testparm pode imprimir avisos antes do dump; comeca na primeira secao
    for index, line in enumerate(lines):
        if line.lstrip().startswith("["):
            lines = lines[index:]
            break
    parser = configparser.ConfigParser(
        strict=False, interpolation=None, allow_no_value=True, delimiters=("=",)
    )
    parser.optionxform = str
    parser.read_string("\n".join(lines))
    return parser


def _dir_size_bytes(path: str, exclude: str | None = None, timeout: int = 120) -> int:
    if not path or not os.path.isdir(path):
        return 0
    args = ["du", "-sb"]
    if exclude:
        args.append(f"--exclude={exclude}")
    args.append(path)
    try:
        return int(run(args, timeout=timeout).split()[0])
    except (AgentError, ValueError, IndexError):
        return 0


def _btrfs_du_bytes(path: str) -> int:
    """Tamanho aproximado do diretorio de snapshots Btrfs (inclui extents compartilhados)."""
    if not path or not os.path.isdir(path):
        return 0
    try:
        out = run(["btrfs", "filesystem", "du", "-s", "--raw", path], timeout=180)
    except AgentError:
        return 0
    # Saida: "Total Exclusive Set shared Filename" (bytes com --raw)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            try:
                return int(parts[0])
            except ValueError:
                continue
    return 0


def _snapshot_extra_bytes(path: str, snapdir: str) -> int:
    """Espaco adicional ocupado por snapshots rsync dentro do share.

    O ``du`` conta hardlinks uma unica vez; a diferenca entre o total do
    share e o live (sem ``.snapshots``) e o extra atribuido aos snapshots.
    """
    if not snapdir or not os.path.isdir(snapdir):
        return 0
    total = _dir_size_bytes(path)
    live = _dir_size_bytes(path, exclude=".snapshots")
    return max(0, total - live)


def op_list_shares(include_size=False, **_):
    parser = _parse_smb_conf()
    shares = []
    for section in parser.sections():
        if section.lower() == "global" or section.lower() in RESERVED_SHARES:
            continue
        if parser.getboolean(section, "printable", fallback=False):
            continue
        path = parser.get(section, "path", fallback="")
        if section in DENY_SNAPSHOT:
            backend = "none"
            snapdir = ""
        else:
            backend = snapshot_backend_for(path) if path else "none"
            snapdir = snapshot_dir_for(section, path, backend) if backend != "none" else ""
        item = {
            "name": section,
            "path": path,
            "comment": parser.get(section, "comment", fallback=""),
            "valid_users": parser.get(section, "valid users", fallback=""),
            "read_only": parser.getboolean(section, "read only", fallback=False),
            "write_list": parser.get(section, "write list", fallback=""),
            "force_group": parser.get(section, "force group", fallback=""),
            "browseable": parser.getboolean(section, "browseable", fallback=True),
            "backend": backend,
            "snapdir": snapdir,
        }
        if include_size:
            live = _dir_size_bytes(path, exclude=".snapshots")
            if backend == "btrfs":
                snapshots = _btrfs_du_bytes(snapdir)
            elif backend == "rsync":
                snapshots = _snapshot_extra_bytes(path, snapdir)
            else:
                snapshots = 0
            item["size"] = live
            item["size_snapshots"] = snapshots
            item["size_total"] = live + snapshots
        shares.append(item)
    return sorted(shares, key=lambda item: item["name"])


def _validate_share_path(path: str) -> str:
    path = (path or "").rstrip("/")
    if not path.startswith("/"):
        raise AgentError("Caminho deve ser absoluto")
    if not any(path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
        raise AgentError(
            "Caminho nao permitido. Use: " + ", ".join(ALLOWED_PATH_PREFIXES)
        )
    if ".." in Path(path).parts:
        raise AgentError("Caminho invalido")
    return path


def _ensure_group(name: str) -> None:
    if not getent_group(name):
        run(["groupadd", name])


def _ensure_subvolume(path: str) -> None:
    """Cria o share como subvolume Btrfs (necessario para snapshot nativo)."""
    if os.path.exists(path):
        try:
            run(["btrfs", "subvolume", "show", path], timeout=10)
        except AgentError as exc:
            raise AgentError(
                f"{path} existe mas nao e um subvolume Btrfs; snapshots nativos exigem subvolume"
            ) from exc
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    run(["btrfs", "subvolume", "create", path])


def op_create_share(name: str, path: str, comment="", snapshot=False, snapshot_keep=7, private=False, **_):
    if not SHARE_RE.match(name or ""):
        raise AgentError("Nome de share invalido (1-32: A-Z a-z 0-9 _ -)")
    if name.lower() in RESERVED_SHARES:
        raise AgentError(f"Nome reservado: {name}")
    if snapshot and name in DENY_SNAPSHOT:
        raise AgentError(f"Snapshot nao permitido para {name} (denylist)")
    path = _validate_share_path(path)

    if os.path.abspath(path) == os.path.abspath(STORAGE_ROOT):
        raise AgentError("Nao crie share na raiz do volume; use um subdiretorio/subvolume")
    if os.path.abspath(path).startswith(os.path.abspath(SNAPSHOT_ROOT) + os.sep):
        raise AgentError("Nao crie share dentro de .snapshots")

    parser = _parse_smb_conf()
    if parser.has_section(name):
        raise AgentError(f"Share ja existe: {name}")

    backend = "none"
    snapdir = ""
    if snapshot:
        backend = snapshot_backend_for(path)
        if backend == "none":
            raise AgentError(
                f"Snapshots indisponiveis para {path}; backend={SNAPSHOT_BACKEND}"
            )
        if backend == "btrfs":
            if not os.path.ismount(STORAGE_ROOT):
                raise AgentError(
                    f"{STORAGE_ROOT} nao esta montado; monte o Btrfs antes de criar snapshots"
                )
            _ensure_subvolume(path)
        else:
            if not shutil.which("rsync"):
                raise AgentError("rsync nao encontrado; snapshots rsync indisponiveis")
            os.makedirs(path, exist_ok=True)
        snapdir = snapshot_dir_for(name, path, backend)
        os.makedirs(snapdir, exist_ok=True)
        os.chmod(snapdir, 0o755)
    else:
        os.makedirs(path, exist_ok=True)

    file_group = name
    ro_group = f"{name}_ro"
    rw_group = f"{name}_rw"
    for group in (file_group, ro_group, rw_group):
        _ensure_group(group)

    owner = SHARE_OWNER if _user_exists(SHARE_OWNER) else "root"
    shutil.chown(path, user=owner, group=file_group)
    os.chmod(path, 0o2775)

    section = (
        f"\n[{name}]\n"
        f"    comment = {comment or name}\n"
        f"    path = {path}\n"
        f"    valid users = @{ro_group} @{rw_group}\n"
        f"    read only = yes\n"
        f"    write list = @{rw_group}\n"
        f"    force group = {file_group}\n"
        f"    create mask = 0664\n"
        f"    force create mode = 0664\n"
        f"    directory mask = 2775\n"
        f"    force directory mode = 2775\n"
        f"    hide dot files = yes\n"
    )
    if private:
        section += "    browseable = no\n"
    if snapshot:
        section += (
            "    vfs objects = shadow_copy2\n"
            f"    shadow:snapdir = {snapdir}\n"
            f"    shadow:basedir = {path}\n"
            "    shadow:format = @GMT-%Y.%m.%d-%H.%M.%S\n"
            "    shadow:sort = desc\n"
            "    shadow:localtime = yes\n"
        )

    backup = f"{SMB_CONF}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(SMB_CONF, backup)
    with open(SMB_CONF, "a", encoding="utf-8") as fh:
        fh.write(section)

    try:
        run(["testparm", "-s"])
    except AgentError:
        shutil.copy2(backup, SMB_CONF)
        raise AgentError("Configuracao invalida; smb.conf restaurado")

    try:
        run(["smbcontrol", "smbd", "reload-config"])
    except AgentError as exc:
        log(f"WARN reload: {exc}")

    if snapshot:
        policy = load_policies()
        policy[name] = {
            "path": path,
            "enabled": True,
            "keep": int(snapshot_keep or 7),
            "backend": backend,
            "snapdir": snapdir,
        }
        save_policies(policy)

    log(f"CREATE_SHARE {name} path={path}")
    return {"name": name, "path": path, "groups": [ro_group, rw_group], "backup": backup}


def load_policies() -> dict:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(SNAP_CONFIG):
        save_policies(DEFAULT_POLICY)
        return json.loads(json.dumps(DEFAULT_POLICY))
    with open(SNAP_CONFIG, encoding="utf-8") as fh:
        return json.load(fh)


def save_policies(policy: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = f"{SNAP_CONFIG}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(policy, fh, indent=2, sort_keys=True)
    os.replace(tmp, SNAP_CONFIG)


def _snapshot_dir(share: str) -> tuple[str, str, str]:
    policy = load_policies()
    if share not in policy:
        raise AgentError(f"Share sem politica de snapshot: {share}")
    if share in DENY_SNAPSHOT:
        raise AgentError(f"Snapshot proibido para {share} (denylist)")
    if not policy[share].get("enabled"):
        raise AgentError(f"Politica de snapshot desativada para {share}")
    src = policy[share]["path"]
    backend = policy[share].get("backend") or snapshot_backend_for(src)
    if backend == "none":
        raise AgentError(f"Snapshots indisponiveis para {share}")
    if backend == "btrfs":
        if not os.path.ismount(STORAGE_ROOT):
            raise AgentError(f"{STORAGE_ROOT} nao esta montado; snapshots abortados")
        try:
            run(["btrfs", "subvolume", "show", src], timeout=10)
        except AgentError as exc:
            raise AgentError(
                f"{src} nao e um subvolume Btrfs; recrie o share com snapshot habilitado"
            ) from exc
    snapdir = policy[share].get("snapdir") or snapshot_dir_for(share, src, backend)
    os.makedirs(snapdir, exist_ok=True)
    os.chmod(snapdir, 0o755)
    return src, snapdir, backend


def _snapshot_list(snapdir: str) -> list[str]:
    if not os.path.isdir(snapdir):
        return []
    return sorted(
        name for name in os.listdir(snapdir) if SNAP_RE.match(name) and os.path.isdir(os.path.join(snapdir, name))
    )


def _btrfs_delete(path: str) -> None:
    try:
        run(["btrfs", "subvolume", "delete", path], timeout=120)
    except AgentError:
        shutil.rmtree(path, ignore_errors=True)


def _delete_snapshot(path: str, backend: str) -> None:
    if backend == "btrfs":
        _btrfs_delete(path)
    else:
        shutil.rmtree(path, ignore_errors=True)


def op_snapshot_usage(include_size=True, **_):
    policy = load_policies()
    result = []
    for share, cfg in sorted(policy.items()):
        src = cfg.get("path", "")
        if share in DENY_SNAPSHOT:
            # Denylist: nao varre o snapdir nem devolve snapshots.
            result.append(
                {
                    "share": share,
                    "path": src,
                    "enabled": False,
                    "keep": int(cfg.get("keep", 0)),
                    "count": 0,
                    "size": 0,
                    "backend": "none",
                    "snapdir": "",
                    "snapshots": [],
                }
            )
            continue
        enabled = bool(cfg.get("enabled"))
        backend = cfg.get("backend") or (snapshot_backend_for(src) if src else "none")
        snapdir = cfg.get("snapdir") or (
            snapshot_dir_for(share, src, backend) if src and backend != "none" else ""
        )
        # Nunca varre share desativado.
        names = _snapshot_list(snapdir) if (enabled and snapdir) else []
        if include_size and enabled and snapdir and backend == "btrfs":
            # Btrfs compartilha extents entre snapshots; o numero e aproximado.
            total_size = _btrfs_du_bytes(snapdir)
        elif include_size and enabled and snapdir and backend == "rsync":
            total_size = _snapshot_extra_bytes(src, snapdir)
        else:
            total_size = 0
        snapshots = []
        for name in reversed(names):
            try:
                stamp = dt.datetime.strptime(name, "@GMT-%Y.%m.%d-%H.%M.%S")
                mtime = stamp.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                mtime = ""
            snapshots.append({"name": name, "mtime": mtime})
        result.append(
            {
                "share": share,
                "path": src,
                "enabled": bool(cfg.get("enabled")),
                "keep": int(cfg.get("keep", 0)),
                "count": len(names),
                "size": total_size,
                "backend": backend,
                "snapdir": snapdir,
                "snapshots": snapshots,
            }
        )
    return result


def op_snapshot_list(share: str, **_):
    _, snapdir, backend = _snapshot_dir(share)
    return {
        "share": share,
        "backend": backend,
        "snapdir": snapdir,
        "snapshots": _snapshot_list(snapdir),
    }


def op_snapshot_create(share: str, **_):
    src, snapdir, backend = _snapshot_dir(share)
    names = _snapshot_list(snapdir)
    stamp = dt.datetime.now().strftime("@GMT-%Y.%m.%d-%H.%M.%S")
    dest = os.path.join(snapdir, stamp)
    if os.path.exists(dest):
        raise AgentError(f"Snapshot ja existe: {stamp}")

    try:
        if backend == "btrfs":
            run(["btrfs", "subvolume", "snapshot", "-r", src, dest], timeout=1800)
        else:
            if not shutil.which("rsync"):
                raise AgentError("rsync nao encontrado; snapshots rsync indisponiveis")
            args = [
                "rsync",
                "-aHAX",
                "--numeric-ids",
                "--delete",
                "--exclude=.snapshots",
            ]
            if names:
                args.append(f"--link-dest={os.path.join(snapdir, names[-1])}")
            args.extend([f"{src}/", f"{dest}/"])
            run(args, timeout=1800)
    except AgentError:
        _delete_snapshot(dest, backend)
        raise

    keep = max(1, int(load_policies()[share].get("keep", 7)))
    names = _snapshot_list(snapdir)
    for old in names[: max(0, len(names) - keep)]:
        _delete_snapshot(os.path.join(snapdir, old), backend)
        log(f"PRUNE {share}/{old}")
    log(f"SNAPSHOT {share} {stamp}")
    return {"share": share, "name": stamp, "backend": backend}


def op_snapshot_delete(share: str, name: str, **_):
    if not SNAP_RE.match(name or ""):
        raise AgentError("Nome de snapshot invalido")
    _, snapdir, backend = _snapshot_dir(share)
    target = os.path.join(snapdir, name)
    real = os.path.realpath(target)
    if os.path.dirname(real) != os.path.realpath(snapdir):
        raise AgentError("Caminho de snapshot invalido")
    if not os.path.isdir(real):
        raise AgentError(f"Snapshot nao encontrado: {name}")
    _delete_snapshot(real, backend)
    log(f"DELETE_SNAPSHOT {share}/{name}")
    return {"share": share, "name": name}


def _load_backup_config() -> dict:
    path = Path(BACKUP_CONFIG)
    if not path.exists():
        return {"disks": [], "jobs": []}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentError(f"Configuracao de backup invalida: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentError("Configuracao de backup invalida")
    data.setdefault("disks", [])
    data.setdefault("jobs", [])
    return data


def _save_backup_config(data: dict) -> None:
    path = Path(BACKUP_CONFIG)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _backup_jobs_for_disk(config: dict, disk: dict) -> list[dict]:
    jobs = []
    for job in config.get("jobs", []):
        if (
            job.get("disk_uuid") == disk.get("uuid")
            or job.get("disk_serial") == disk.get("serial")
            or job.get("device") == disk.get("device")
        ):
            jobs.append(job)
    return jobs


def _backup_disks(config: dict) -> list[dict]:
    raw = run(
        [
            "lsblk",
            "-J",
            "-o",
            "NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,TRAN",
        ]
    )
    data = json.loads(raw)
    disks = []

    def descendants(device: dict) -> list[dict]:
        result = []
        for child in device.get("children") or []:
            result.append(child)
            result.extend(descendants(child))
        return result

    for device in data.get("blockdevices", []):
        name = device.get("name", "")
        if device.get("type") != "disk" or name.startswith("loop"):
            continue
        path = f"/dev/{name}"
        mounts = _collect_mounts(device)
        children = descendants(device)
        all_parts = [device] + children
        fstypes = [item.get("fstype") for item in all_parts if item.get("fstype")]
        labels = [item.get("label") for item in all_parts if item.get("label")]
        uuids = [item.get("uuid") for item in all_parts if item.get("uuid")]
        serial = (device.get("serial") or "").strip()
        model = (device.get("model") or "").strip()
        uuid = uuids[0] if uuids else None
        fstype = fstypes[0] if fstypes else None
        label = labels[0] if labels else None
        has_data = bool(fstypes or uuids or children)
        has_filesystem = bool(fstypes or uuids or children)
        system = any(mount == "/" for mount in mounts)
        raid = any(item == "linux_raid_member" for item in fstypes) or any(
            child.get("name", "").startswith("md") for child in children
        )
        configured_entry = None
        for entry in config.get("disks", []):
            if (
                (entry.get("serial") and entry.get("serial") == serial)
                or entry.get("device") == path
                or (entry.get("uuid") and entry.get("uuid") == uuid)
            ):
                configured_entry = entry
                break
        configured = configured_entry is not None
        jobs = _backup_jobs_for_disk(
            config,
            configured_entry
            or {"uuid": uuid, "serial": serial, "device": path},
        )
        candidate = not system and not raid and not mounts
        reason = ""
        if system:
            reason = "disco do sistema"
        elif raid:
            reason = "membro de RAID"
        elif mounts:
            reason = "montado em " + ", ".join(mounts)
        if configured:
            required = f"RECONFIGURAR {path}"
        elif has_filesystem:
            required = f"APAGAR {path}"
        else:
            required = f"FORMATAR {path}"

        warnings = []
        if configured:
            warning = "Disco já configurado no backup"
            if jobs:
                warning += ": " + ", ".join(job.get("name", "?") for job in jobs)
            warnings.append(warning)
        if has_filesystem:
            detail = f"Contém filesystem {fstype or 'desconhecido'}"
            if label:
                detail += f" (label {label})"
            warnings.append(detail)
        if not candidate:
            warnings.append(f"Indisponível: {reason}")

        disks.append(
            {
                "name": name,
                "path": path,
                "size": device.get("size"),
                "model": model,
                "serial": serial,
                "tran": device.get("tran"),
                "fstype": fstype,
                "label": label,
                "uuid": uuid,
                "mounts": mounts,
                "has_data": has_data,
                "has_filesystem": has_filesystem,
                "configured": configured,
                "jobs": [job.get("name") for job in jobs],
                "repo": (configured_entry or {}).get("repo"),
                "mountpoint": (configured_entry or {}).get("mountpoint"),
                "candidate": candidate,
                "reason": reason,
                "required_phrase": required,
                "extra_confirmation": configured or has_filesystem,
                "warnings": warnings,
            }
        )
    return sorted(disks, key=lambda item: item["name"])


def op_backup_overview(**_):
    config = _load_backup_config()
    return {
        "disks": _backup_disks(config),
        "jobs": _backup_jobs(config),
        "backup_root": BACKUP_ROOT,
        "restic": shutil.which("restic") is not None,
    }


def op_backup_snapshots(**_):
    if not shutil.which("restic"):
        raise AgentError("restic nao esta instalado no host")
    config = _load_backup_config()
    result = []
    errors = []
    for disk in config.get("disks", []):
        repo = disk.get("repo")
        key_file = disk.get("key_file")
        label = disk.get("label") or disk.get("uuid") or "backup"
        if not repo or not key_file or not os.path.isfile(key_file):
            errors.append(f"{label}: repositorio ou chave ausente")
            continue
        try:
            raw = run(
                [
                    "restic",
                    "-r",
                    repo,
                    "--password-file",
                    key_file,
                    "snapshots",
                    "--json",
                ],
                timeout=120,
            )
            snapshots = json.loads(raw)
        except (AgentError, json.JSONDecodeError) as exc:
            errors.append(f"{label}: {exc}")
            continue
        for snap in snapshots:
            summary = snap.get("summary") or {}
            paths = snap.get("paths") or []
            try:
                browse_path = os.path.commonpath(paths) if paths else "/"
            except ValueError:
                browse_path = "/"
            result.append(
                {
                    "disk_label": label,
                    "disk_uuid": disk.get("uuid"),
                    "id": snap.get("id"),
                    "short_id": snap.get("short_id") or (snap.get("id") or "")[:8],
                    "time": snap.get("time"),
                    "hostname": snap.get("hostname"),
                    "paths": paths,
                    "browse_path": browse_path,
                    "tags": snap.get("tags") or [],
                    "files": summary.get("total_files_processed", 0),
                    "bytes": summary.get("total_bytes_processed", 0),
                    "added_bytes": summary.get("data_added_packed", 0),
                    "empty": summary.get("total_files_processed", 0) == 0,
                }
            )
    return {
        "snapshots": sorted(
            result, key=lambda item: item.get("time") or "", reverse=True
        ),
        "errors": errors,
    }


def _backup_disk_by_uuid(disk_uuid: str) -> dict:
    for disk in _load_backup_config().get("disks", []):
        if disk.get("uuid") == disk_uuid:
            if not disk.get("repo") or not disk.get("key_file"):
                raise AgentError(f"Disco sem repositorio/chave: {disk_uuid}")
            if not os.path.isfile(disk["key_file"]):
                raise AgentError(f"Chave do restic ausente: {disk['key_file']}")
            return disk
    raise AgentError(f"Disco de backup nao encontrado: {disk_uuid}")


def _validate_restic_snapshot(snapshot_id: str) -> str:
    if not RESTIC_SNAPSHOT_RE.match(snapshot_id or ""):
        raise AgentError("ID de snapshot restic invalido")
    return snapshot_id


def _validate_restic_path(path: str) -> str:
    path = (path or "/mnt/nas").strip()
    if not path.startswith("/") or ".." in PurePosixPath(path).parts:
        raise AgentError("Caminho de backup invalido")
    return str(PurePosixPath(path))


def op_backup_ls(disk_uuid: str, snapshot_id: str, path: str = "/mnt/nas", **_):
    if not shutil.which("restic"):
        raise AgentError("restic nao esta instalado no host")
    disk = _backup_disk_by_uuid(disk_uuid)
    snapshot_id = _validate_restic_snapshot(snapshot_id)
    path = _validate_restic_path(path)
    raw = run(
        [
            "restic",
            "-r",
            disk["repo"],
            "--password-file",
            disk["key_file"],
            "ls",
            "--json",
            snapshot_id,
            path,
        ],
        timeout=120,
    )
    entries = []
    snapshot = {}
    for line in raw.splitlines():
        try:
            node = json.loads(line)
        except json.JSONDecodeError:
            continue
        if node.get("message_type") == "snapshot":
            snapshot = {
                "id": node.get("id"),
                "short_id": node.get("short_id"),
                "time": node.get("time"),
                "hostname": node.get("hostname"),
                "paths": node.get("paths") or [],
                "tags": node.get("tags") or [],
            }
            continue
        if node.get("message_type") != "node":
            continue
        node_path = node.get("path") or ""
        if str(PurePosixPath(node_path).parent) != path:
            continue
        entries.append(
            {
                "name": node.get("name") or PurePosixPath(node_path).name,
                "path": node_path,
                "type": node.get("type"),
                "size": node.get("size"),
                "mtime": node.get("mtime"),
                "permissions": node.get("permissions"),
            }
        )
    entries.sort(key=lambda item: (item["type"] != "dir", item["name"].casefold()))
    return {
        "disk_uuid": disk_uuid,
        "snapshot_id": snapshot_id,
        "path": path,
        "parent": str(PurePosixPath(path).parent),
        "snapshot": snapshot,
        "entries": entries,
    }


def _cleanup_downloads(max_age: int = 86400) -> None:
    root = Path(DOWNLOAD_DIR)
    if not root.is_dir():
        return
    cutoff = time.time() - max_age
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue


def _validate_backup_query(query: str) -> tuple[str, str]:
    query = (query or "").strip()
    if not query or len(query) > 120 or any(ord(char) < 32 for char in query):
        raise AgentError("Busca invalida (1-120 caracteres, sem controles)")
    pattern = query if any(char in query for char in "*?[") else f"*{query}*"
    return query, pattern


def op_backup_search(
    disk_uuid: str,
    snapshot_id: str,
    query: str,
    limit: int = 200,
    **_,
):
    if not shutil.which("restic"):
        raise AgentError("restic nao esta instalado no host")
    disk = _backup_disk_by_uuid(disk_uuid)
    snapshot_id = _validate_restic_snapshot(snapshot_id)
    query, pattern = _validate_backup_query(query)
    limit = max(1, min(int(limit), 500))
    raw = run(
        [
            "restic",
            "-r",
            disk["repo"],
            "--password-file",
            disk["key_file"],
            "find",
            "--snapshot",
            snapshot_id,
            "--json",
            "--ignore-case",
            pattern,
        ],
        timeout=180,
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentError("Resposta invalida do restic find") from exc
    if not isinstance(payload, list):
        raise AgentError("Resposta invalida do restic find")
    matches = []
    total = 0
    for item in payload:
        item_matches = item.get("matches") or []
        total += int(item.get("hits") or len(item_matches))
        for node in item_matches:
            node_path = node.get("path") or ""
            if not node_path:
                continue
            matches.append(
                {
                    "name": node.get("name") or PurePosixPath(node_path).name,
                    "path": node_path,
                    "parent": str(PurePosixPath(node_path).parent),
                    "type": node.get("type"),
                    "size": node.get("size"),
                    "mtime": node.get("mtime"),
                    "permissions": node.get("permissions"),
                }
            )
    return {
        "disk_uuid": disk_uuid,
        "snapshot_id": snapshot_id,
        "query": query,
        "pattern": pattern,
        "total": total,
        "truncated": total > limit,
        "matches": matches[:limit],
    }


def op_backup_download(disk_uuid: str, snapshot_id: str, path: str, **_):
    if not shutil.which("restic"):
        raise AgentError("restic nao esta instalado no host")
    disk = _backup_disk_by_uuid(disk_uuid)
    snapshot_id = _validate_restic_snapshot(snapshot_id)
    path = _validate_restic_path(path)
    _cleanup_downloads()
    filename = PurePosixPath(path).name or "download"
    token = dt.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
    target_dir = Path(DOWNLOAD_DIR) / token
    target_dir.mkdir(parents=True, exist_ok=False)
    os.chmod(target_dir.parent, 0o700)
    os.chmod(target_dir, 0o700)
    target = target_dir / filename
    with open(target, "wb") as output:
        proc = subprocess.run(
            [
                "restic",
                "-r",
                disk["repo"],
                "--password-file",
                disk["key_file"],
                "dump",
                snapshot_id,
                path,
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=600,
            check=False,
        )
    if proc.returncode != 0:
        shutil.rmtree(target_dir, ignore_errors=True)
        detail = (proc.stderr or b"").decode("utf-8", errors="replace").strip()[:500]
        raise AgentError(f"restic dump falhou: {detail or proc.returncode}")
    data_root = Path(DATA_DIR).resolve()
    target_res = target.resolve()
    try:
        relative = target_res.relative_to(data_root)
    except ValueError as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise AgentError("DOWNLOAD_DIR fora de DATA_DIR") from exc
    return {
        "relative": str(relative),
        "filename": filename,
        "size": target.stat().st_size,
    }


def op_backup_disk_setup(
    device: str,
    label: str,
    confirmation: str,
    allow_existing: bool = False,
    **_,
):
    device = (device or "").strip()
    label = (label or "").strip().lower()
    confirmation = (confirmation or "").strip()
    if not BLOCK_DEVICE_RE.match(device):
        raise AgentError("Dispositivo invalido (use /dev/sdX, /dev/nvmeXnY ou similar)")
    if not BACKUP_LABEL_RE.match(label):
        raise AgentError("Label invalida (1-16 caracteres: a-z, 0-9, _ ou -)")
    if not shutil.which("restic"):
        raise AgentError("restic nao esta instalado no host")
    if not shutil.which("parted"):
        raise AgentError("parted nao esta instalado no host")

    config = _load_backup_config()
    disk = next((item for item in _backup_disks(config) if item["path"] == device), None)
    if disk is None:
        raise AgentError(f"Disco nao encontrado: {device}")
    if not disk["candidate"]:
        raise AgentError(f"Disco indisponivel: {disk['reason']}")
    if disk["extra_confirmation"] and not allow_existing:
        raise AgentError("Confirmacao extra obrigatoria para disco nao vazio/configurado")
    if confirmation != disk["required_phrase"]:
        raise AgentError(
            f"Confirmacao incorreta. Digite exatamente: {disk['required_phrase']}"
        )

    holders = Path(f"/sys/block/{disk['name']}/holders")
    if holders.is_dir() and any(holders.iterdir()):
        raise AgentError("Disco possui holders ativos; nao vou formatar")

    mountpoint = f"{BACKUP_ROOT}/{label}"
    repo = f"{mountpoint}/restic"
    Path(BACKUP_ROOT).mkdir(parents=True, exist_ok=True)
    Path(mountpoint).mkdir(parents=True, exist_ok=True)

    run(["wipefs", "-a", device], timeout=60)
    run(
        [
            "parted",
            "-s",
            device,
            "mklabel",
            "gpt",
            "mkpart",
            "primary",
            "ext4",
            "1MiB",
            "100%",
        ],
        timeout=120,
    )
    run(["udevadm", "settle"], timeout=30)
    partition = f"{device}1"
    if not os.path.exists(partition):
        raise AgentError(f"Particao nao criada: {partition}")
    run(["mkfs.ext4", "-F", "-L", label, partition], timeout=600)
    run(["udevadm", "settle"], timeout=30)
    uuid = run(["blkid", "-s", "UUID", "-o", "value", partition]).strip()
    if not UUID_RE.match(uuid):
        raise AgentError(f"UUID invalido apos formatar: {uuid!r}")

    fstab = Path("/etc/fstab")
    text = fstab.read_text()
    line = (
        f"UUID={uuid} {mountpoint} ext4 "
        "defaults,noatime,nofail,x-systemd.device-timeout=10s 0 2\n"
    )
    lines = []
    for existing in text.splitlines():
        fields = existing.split()
        if fields and not existing.lstrip().startswith("#") and len(fields) >= 2:
            if fields[1] == mountpoint or fields[0] == f"UUID={uuid}":
                continue
        lines.append(existing)
    body = "\n".join(lines).rstrip()
    fstab.write_text((body + "\n" if body else "") + line)
    run(["systemctl", "daemon-reload"], timeout=30)
    run(["mount", mountpoint], timeout=60)

    Path(repo).mkdir(parents=True, exist_ok=True)
    os.chmod(repo, 0o700)
    secret_dir = Path(BACKUP_SECRETS)
    secret_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(secret_dir, 0o700)
    recovery_password = secrets.token_urlsafe(32)
    key_file = secret_dir / f"{uuid}.key"
    key_file.write_text(recovery_password + "\n")
    os.chmod(key_file, 0o600)
    run(
        [
            "restic",
            "-r",
            repo,
            "--password-file",
            str(key_file),
            "init",
        ],
        timeout=300,
    )

    entry = {
        "device": device,
        "serial": disk.get("serial"),
        "uuid": uuid,
        "label": label,
        "mountpoint": mountpoint,
        "repo": repo,
        "key_file": str(key_file),
        "configured_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    config["disks"] = [
        item
        for item in config.get("disks", [])
        if not (
            item.get("uuid") == uuid
            or item.get("device") == device
            or (disk.get("serial") and item.get("serial") == disk.get("serial"))
        )
    ]
    config["disks"].append(entry)
    _save_backup_config(config)
    log(f"BACKUP_DISK_SETUP {device} {label} {uuid}")
    return {
        "device": device,
        "label": label,
        "uuid": uuid,
        "mountpoint": mountpoint,
        "repo": repo,
        "key_file": str(key_file),
        "recovery_password": recovery_password,
    }


def op_backup_secret(uuid: str, **_):
    config = _load_backup_config()
    entry = next(
        (item for item in config.get("disks", []) if item.get("uuid") == uuid),
        None,
    )
    if entry is None:
        raise AgentError("Disco de backup nao encontrado")
    key_file = Path(entry.get("key_file") or "")
    secret_root = Path(BACKUP_SECRETS).resolve()
    try:
        real = key_file.resolve()
    except OSError as exc:
        raise AgentError(f"Caminho de segredo invalido: {exc}") from exc
    if secret_root not in real.parents:
        raise AgentError("Caminho de segredo fora do diretorio permitido")
    if not real.is_file():
        raise AgentError("Arquivo de senha do restic nao encontrado")
    password = real.read_text().strip()
    if not password:
        raise AgentError("Senha do restic vazia")
    log(f"BACKUP_SECRET_REVEAL {uuid}")
    return {
        "uuid": uuid,
        "label": entry.get("label"),
        "device": entry.get("device"),
        "repo": entry.get("repo"),
        "password": password,
    }


def _read_backup_status(name: str) -> dict:
    path = Path(BACKUP_STATUS_DIR) / f"{name}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _next_run(schedule: dict | None) -> str | None:
    if not schedule:
        return None
    try:
        hour, minute = [int(part) for part in schedule["time"].split(":")]
    except (KeyError, ValueError, AttributeError):
        return None
    now = dt.datetime.now()
    frequency = schedule.get("frequency")
    if frequency == "daily":
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += dt.timedelta(days=1)
    elif frequency == "weekly":
        try:
            weekday = int(schedule.get("weekday", 0))
        except (TypeError, ValueError):
            return None
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        candidate += dt.timedelta(days=(weekday - now.weekday()) % 7)
        if candidate <= now:
            candidate += dt.timedelta(days=7)
    elif frequency == "monthly":
        try:
            monthday = int(schedule.get("monthday", 1))
        except (TypeError, ValueError):
            return None
        candidate = now.replace(
            day=monthday, hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= now:
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            candidate = candidate.replace(year=year, month=month)
    else:
        return None
    return candidate.isoformat(timespec="minutes")


def _backup_jobs(config: dict) -> list[dict]:
    jobs = []
    disks = {item.get("uuid"): item for item in config.get("disks", [])}
    for job in config.get("jobs", []):
        item = dict(job)
        status = _read_backup_status(job.get("name", ""))
        item["status"] = status
        item["last_run_label"] = (
            status.get("finished_at") or status.get("started_at") or ""
        ).replace("T", " ")[:16]
        next_run = _next_run(job.get("schedule")) if job.get("enabled") else None
        item["next_run"] = next_run
        item["next_run_label"] = (next_run or "").replace("T", " ")[:16]
        disk = disks.get(job.get("disk_uuid"))
        item["disk_label"] = (disk or {}).get("label") or (disk or {}).get("device") or "—"
        jobs.append(item)
    return sorted(jobs, key=lambda item: item.get("name", ""))


def _apply_backup_timer(name: str, enabled: bool, on_calendar: str) -> None:
    service_template = Path("/etc/systemd/system/homelab-restic-backup@.service")
    if not service_template.is_file():
        raise AgentError(
            "Servico homelab-restic-backup@.service ausente; rode sudo ./install-agent.sh"
        )
    timer_name = f"homelab-restic-backup-{name}.timer"
    timer_path = Path("/etc/systemd/system") / timer_name
    if enabled:
        timer_path.write_text(
            "[Unit]\n"
            f"Description=Homelab restic backup timer {name}\n\n"
            "[Timer]\n"
            f"OnCalendar={on_calendar}\n"
            "Persistent=true\n"
            f"Unit=homelab-restic-backup@{name}.service\n\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        )
        os.chmod(timer_path, 0o644)
        run(["systemctl", "daemon-reload"], timeout=30)
        try:
            run(["systemctl", "enable", "--now", timer_name], timeout=30)
        except AgentError:
            timer_path.unlink(missing_ok=True)
            run_optional(["systemctl", "daemon-reload"], timeout=30)
            raise
    else:
        run_optional(["systemctl", "disable", "--now", timer_name], timeout=30)
        timer_path.unlink(missing_ok=True)
        run(["systemctl", "daemon-reload"], timeout=30)


def op_backup_job_save(job: dict, **_):
    if not isinstance(job, dict):
        raise AgentError("Job invalido")
    name = (job.get("name") or "").strip().lower()
    if not JOB_RE.match(name):
        raise AgentError("Nome do job invalido (a-z, 0-9, _ ou -, ate 32)")
    config = _load_backup_config()
    disk_uuid = (job.get("disk_uuid") or "").strip()
    disk = next(
        (item for item in config.get("disks", []) if item.get("uuid") == disk_uuid),
        None,
    )
    if disk is None:
        raise AgentError("Selecione um disco de backup configurado")

    shares = {item["name"]: item["path"] for item in op_list_shares()}
    source_names = job.get("sources") or []
    if not isinstance(source_names, list):
        raise AgentError("Fontes invalidas")
    source_names = [str(item) for item in source_names]
    source_paths = []
    for share_name in source_names:
        path = shares.get(share_name)
        if not path:
            raise AgentError(f"Share nao encontrado: {share_name}")
        if not os.path.isdir(path):
            raise AgentError(f"Pasta do share nao existe: {path}")
        source_paths.append(path)
    if not source_paths:
        raise AgentError("Selecione pelo menos uma fonte")

    raw_excludes = job.get("excludes") or []
    if isinstance(raw_excludes, str):
        raw_excludes = raw_excludes.splitlines()
    if not isinstance(raw_excludes, list):
        raise AgentError("Exclusoes invalidas")
    excludes = []
    for item in raw_excludes:
        value = str(item).strip()
        if not value:
            continue
        if "\n" in value or "\r" in value or "\0" in value:
            raise AgentError("Exclusao invalida")
        excludes.append(value)
    if len(excludes) > 100:
        raise AgentError("Maximo de 100 exclusoes")

    schedule = job.get("schedule") or {}
    frequency = schedule.get("frequency")
    time_value = (schedule.get("time") or "").strip()
    if not TIME_RE.match(time_value):
        raise AgentError("Horario invalido (use HH:MM)")
    if frequency == "daily":
        on_calendar = f"*-*-* {time_value}:00"
        schedule_label = f"Diário {time_value}"
        weekday = None
        monthday = None
    elif frequency == "weekly":
        try:
            weekday = int(schedule.get("weekday", 0))
        except (TypeError, ValueError) as exc:
            raise AgentError("Dia da semana invalido") from exc
        if weekday < 0 or weekday > 6:
            raise AgentError("Dia da semana invalido")
        on_calendar = f"{WEEKDAYS[weekday]} *-*-* {time_value}:00"
        schedule_label = f"Semanal {WEEKDAYS[weekday]} {time_value}"
        monthday = None
    elif frequency == "monthly":
        try:
            monthday = int(schedule.get("monthday", 1))
        except (TypeError, ValueError) as exc:
            raise AgentError("Dia do mes invalido") from exc
        if monthday < 1 or monthday > 28:
            raise AgentError("Dia do mes deve ficar entre 1 e 28")
        on_calendar = f"*-*-{monthday:02d} {time_value}:00"
        schedule_label = f"Mensal dia {monthday} {time_value}"
        weekday = None
    else:
        raise AgentError("Periodicidade invalida")

    retention = job.get("retention") or {}
    clean_retention = {}
    for key in ("daily", "weekly", "monthly"):
        try:
            value = int(retention.get(key) or 0)
        except (TypeError, ValueError) as exc:
            raise AgentError(f"Retencao invalida: {key}") from exc
        if value < 0 or value > 365:
            raise AgentError(f"Retencao fora do limite: {key}")
        clean_retention[key] = value
    if not any(clean_retention.values()):
        raise AgentError("Configure pelo menos uma retencao maior que zero")

    enabled = bool(job.get("enabled", True))
    existing = next(
        (item for item in config.get("jobs", []) if item.get("name") == name), None
    )
    now = dt.datetime.now().isoformat(timespec="seconds")
    new_job = {
        "name": name,
        "disk_uuid": disk_uuid,
        "sources": source_names,
        "source_paths": source_paths,
        "excludes": excludes,
        "schedule": {
            "frequency": frequency,
            "time": time_value,
            "weekday": weekday,
            "monthday": monthday,
            "on_calendar": on_calendar,
            "label": schedule_label,
        },
        "retention": clean_retention,
        "enabled": enabled,
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }
    config["jobs"] = [
        item for item in config.get("jobs", []) if item.get("name") != name
    ] + [new_job]
    _save_backup_config(config)
    try:
        _apply_backup_timer(name, enabled, on_calendar)
    except AgentError:
        new_job["enabled"] = False
        config["jobs"] = [
            item for item in config.get("jobs", []) if item.get("name") != name
        ] + [new_job]
        _save_backup_config(config)
        raise
    log(f"BACKUP_JOB_SAVE {name} {on_calendar} enabled={enabled}")
    return new_job


def op_backup_job_toggle(name: str, enabled: bool, **_):
    config = _load_backup_config()
    job = next(
        (item for item in config.get("jobs", []) if item.get("name") == name), None
    )
    if job is None:
        raise AgentError("Job nao encontrado")
    job["enabled"] = bool(enabled)
    job["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    _save_backup_config(config)
    try:
        _apply_backup_timer(
            name, job["enabled"], job.get("schedule", {}).get("on_calendar", "")
        )
    except AgentError:
        job["enabled"] = False
        _save_backup_config(config)
        raise
    log(f"BACKUP_JOB_TOGGLE {name} enabled={job['enabled']}")
    return job


def op_backup_job_delete(name: str, **_):
    config = _load_backup_config()
    job = next(
        (item for item in config.get("jobs", []) if item.get("name") == name), None
    )
    if job is None:
        raise AgentError("Job nao encontrado")
    config["jobs"] = [
        item for item in config.get("jobs", []) if item.get("name") != name
    ]
    _save_backup_config(config)
    _apply_backup_timer(name, False, "")
    try:
        (Path(BACKUP_STATUS_DIR) / f"{name}.json").unlink(missing_ok=True)
    except OSError:
        pass
    log(f"BACKUP_JOB_DELETE {name}")
    return {"name": name}


def op_backup_job_run(name: str, **_):
    config = _load_backup_config()
    job = next(
        (item for item in config.get("jobs", []) if item.get("name") == name), None
    )
    if job is None:
        raise AgentError("Job nao encontrado")
    run(
        [
            "systemctl",
            "start",
            "--no-block",
            f"homelab-restic-backup@{name}.service",
        ],
        timeout=30,
    )
    log(f"BACKUP_JOB_RUN {name}")
    return {"name": name, "started": True}


# --- backup local do Credenciais (banco + .env, sem restic) ---


def _human_bytes(value: int | float) -> str:
    numero = float(value)
    for unidade in ("B", "KB", "MB", "GB"):
        if numero < 1024:
            return f"{numero:.0f} {unidade}" if unidade == "B" else f"{numero:.1f} {unidade}"
        numero /= 1024
    return f"{numero:.1f} TB"


def _credenciais_config() -> dict:
    base = {
        "time": CREDENCIAIS_TIME,
        "retention_days": CREDENCIAIS_RETENTION_DAYS,
        "db": CREDENCIAIS_DB,
        "env": CREDENCIAIS_ENV,
        "dir": CREDENCIAIS_BACKUP_DIR,
        "container": CREDENCIAIS_CONTAINER,
    }
    caminho = Path(CREDENCIAIS_CONFIG)
    if not caminho.is_file():
        return base
    try:
        dados = json.loads(caminho.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentError(f"Configuracao do backup do Credenciais invalida: {exc}") from exc
    if not isinstance(dados, dict):
        return base
    for chave in list(base):
        valor = dados.get(chave)
        if valor not in (None, ""):
            base[chave] = valor
    try:
        base["retention_days"] = max(1, int(base["retention_days"]))
    except (TypeError, ValueError):
        base["retention_days"] = CREDENCIAIS_RETENTION_DAYS
    if not TIME_RE.match(str(base["time"])):
        base["time"] = CREDENCIAIS_TIME
    return base


def _credenciais_status_read() -> dict:
    caminho = Path(CREDENCIAIS_STATUS)
    if not caminho.is_file():
        return {}
    try:
        dados = json.loads(caminho.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _credenciais_status_write(dados: dict) -> dict:
    caminho = Path(CREDENCIAIS_STATUS)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, indent=2, sort_keys=True))
    os.chmod(temporario, 0o600)
    temporario.replace(caminho)
    return dados


def _credenciais_next_run(config: dict) -> str | None:
    try:
        hora, minuto = [int(parte) for parte in str(config.get("time", "")).split(":")]
    except (ValueError, AttributeError):
        return None
    agora = dt.datetime.now()
    proximo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if proximo <= agora:
        proximo += dt.timedelta(days=1)
    return proximo.isoformat(timespec="minutes")


def _credenciais_arquivo(archive: str) -> Path:
    if not CREDENCIAIS_ARCHIVE_RE.match(archive or ""):
        raise AgentError("Nome de backup invalido")
    config = _credenciais_config()
    caminho = Path(config["dir"]) / archive
    if not caminho.is_file():
        raise AgentError("Backup nao encontrado")
    return caminho


def _credenciais_lista(config: dict) -> list[dict]:
    pasta = Path(config["dir"])
    if not pasta.is_dir():
        return []
    itens = []
    for caminho in pasta.glob("moya-credenciais-*.tar.gz"):
        if not CREDENCIAIS_ARCHIVE_RE.match(caminho.name):
            continue
        try:
            info = caminho.stat()
        except OSError:
            continue
        try:
            criado = dt.datetime.strptime(
                caminho.name[:-7], "moya-credenciais-%Y%m%d-%H%M%S"
            )
        except ValueError:
            criado = dt.datetime.fromtimestamp(info.st_mtime)
        itens.append(
            {
                "name": caminho.name,
                "size_bytes": info.st_size,
                "size": _human_bytes(info.st_size),
                "created_at": criado.isoformat(timespec="seconds"),
                "created_label": criado.strftime("%d/%m/%Y %H:%M"),
                "age_days": max(0, (dt.datetime.now() - criado).days),
            }
        )
    return sorted(itens, key=lambda item: item["name"], reverse=True)


def _credenciais_prune(pasta: Path, dias: int, manter: Path | None = None) -> list[str]:
    limite = dt.datetime.now() - dt.timedelta(days=max(1, int(dias)))
    removidos = []
    for caminho in pasta.glob("moya-credenciais-*.tar.gz"):
        if manter is not None and caminho == manter:
            continue
        if not CREDENCIAIS_ARCHIVE_RE.match(caminho.name):
            continue
        try:
            if dt.datetime.fromtimestamp(caminho.stat().st_mtime) < limite:
                caminho.unlink()
                removidos.append(caminho.name)
        except OSError:
            continue
    for estagio in pasta.glob(".staging-*"):
        try:
            if estagio.is_dir() and dt.datetime.fromtimestamp(
                estagio.stat().st_mtime
            ) < dt.datetime.now() - dt.timedelta(hours=1):
                shutil.rmtree(estagio, ignore_errors=True)
        except OSError:
            continue
    return removidos


def _credenciais_manifesto(copia: Path, arcname: str, origem: Path) -> dict:
    info = origem.stat()
    resumo = hashlib.sha256()
    with open(copia, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return {
        "arcname": arcname,
        "source": str(origem),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": info.st_mode & 0o777,
        "size": copia.stat().st_size,
        "sha256": resumo.hexdigest(),
    }


def _credenciais_backup_run(config: dict | None = None) -> dict:
    config = config or _credenciais_config()
    banco = Path(config["db"])
    ambiente = Path(config["env"])
    if not banco.is_file():
        raise AgentError(f"Banco do Credenciais nao encontrado em {banco}")
    if not ambiente.is_file():
        raise AgentError(f"Arquivo .env do Credenciais nao encontrado em {ambiente}")
    destino = Path(config["dir"])
    destino.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(destino, 0o700)
        if hasattr(os, "chown"):
            os.chown(destino, 0, 0)
    except (OSError, NotImplementedError):
        pass
    inicio = dt.datetime.now()
    nome = f"moya-credenciais-{inicio.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    estagio = Path(tempfile.mkdtemp(prefix=".staging-", dir=destino))
    try:
        copia_banco = estagio / "db.sqlite3"
        origem = sqlite3.connect(banco.resolve().as_uri() + "?mode=ro", uri=True)
        alvo = sqlite3.connect(str(copia_banco))
        try:
            origem.backup(alvo)
        finally:
            alvo.close()
            origem.close()
        os.chmod(copia_banco, 0o600)
        copia_env = estagio / ".env"
        shutil.copyfile(ambiente, copia_env)
        os.chmod(copia_env, 0o600)
        manifesto = {
            "created_at": inicio.isoformat(timespec="seconds"),
            "files": [
                _credenciais_manifesto(copia_banco, "db.sqlite3", banco),
                _credenciais_manifesto(copia_env, ".env", ambiente),
            ],
        }
        (estagio / "manifest.json").write_text(json.dumps(manifesto, indent=2))
        os.chmod(estagio / "manifest.json", 0o600)
        arquivo = destino / nome
        with tarfile.open(arquivo, "w:gz") as pacote:
            for item in ("db.sqlite3", ".env", "manifest.json"):
                pacote.add(estagio / item, arcname=item)
        os.chmod(arquivo, 0o600)
    except (OSError, sqlite3.Error, tarfile.TarError) as exc:
        raise AgentError(f"Falha ao gerar o backup do Credenciais: {exc}") from exc
    finally:
        shutil.rmtree(estagio, ignore_errors=True)
    removidos = _credenciais_prune(destino, config["retention_days"], manter=arquivo)
    fim = dt.datetime.now()
    status = _credenciais_status_write(
        {
            "ok": True,
            "error": "",
            "started_at": inicio.isoformat(timespec="seconds"),
            "finished_at": fim.isoformat(timespec="seconds"),
            "duration_seconds": round((fim - inicio).total_seconds(), 1),
            "archive": nome,
            "size": arquivo.stat().st_size,
            "size_label": _human_bytes(arquivo.stat().st_size),
            "removed": removidos,
            "database": str(banco),
            "env": str(ambiente),
            "retention_days": config["retention_days"],
        }
    )
    log(f"CREDENCIAIS_BACKUP {nome} {status['size_label']}")
    return status


def _credenciais_extrair(arquivo: Path, destino: Path) -> None:
    permitidos = {"db.sqlite3", ".env", "manifest.json"}
    try:
        with tarfile.open(arquivo, "r:gz") as pacote:
            for membro in pacote.getmembers():
                if membro.name not in permitidos or not membro.isfile():
                    raise AgentError(f"Entrada inesperada no backup: {membro.name}")
                origem = pacote.extractfile(membro)
                if origem is None:
                    raise AgentError(f"Nao foi possivel ler {membro.name} do backup")
                alvo = destino / membro.name
                with open(alvo, "wb") as saida:
                    shutil.copyfileobj(origem, saida)
                os.chmod(alvo, 0o600)
    except (OSError, tarfile.TarError) as exc:
        raise AgentError(f"Backup invalido: {exc}") from exc


def _credenciais_conferir(destino: Path) -> dict:
    try:
        manifesto = json.loads((destino / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentError(f"Manifesto do backup invalido: {exc}") from exc
    conferencias = []
    for item in manifesto.get("files", []):
        alvo = destino / item.get("arcname", "")
        if not alvo.is_file():
            conferencias.append(False)
            continue
        resumo = hashlib.sha256()
        with open(alvo, "rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                resumo.update(bloco)
        conferencias.append(resumo.hexdigest() == item.get("sha256"))
    conexao = sqlite3.connect(str(destino / "db.sqlite3"))
    try:
        integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as exc:
        raise AgentError(f"Nao foi possivel verificar o banco: {exc}") from exc
    finally:
        conexao.close()
    return {
        "integrity": integridade,
        "hashes_ok": bool(conferencias) and all(conferencias),
        "manifest": manifesto,
    }


def op_credenciais_backup_overview(**_):
    config = _credenciais_config()
    banco = Path(config["db"])
    ambiente = Path(config["env"])
    rc, saida, _ = run_optional(
        ["systemctl", "is-active", "homelab-credenciais-backup.timer"], timeout=10
    )
    return {
        "available": banco.is_file() and ambiente.is_file(),
        "config": {
            "time": config["time"],
            "retention_days": config["retention_days"],
            "db": config["db"],
            "env": config["env"],
            "dir": config["dir"],
            "container": config["container"],
        },
        "sources": [
            {
                "name": "Banco SQLite",
                "path": config["db"],
                "ok": banco.is_file(),
                "size": _human_bytes(banco.stat().st_size) if banco.is_file() else "-",
            },
            {
                "name": "Variaveis de ambiente",
                "path": config["env"],
                "ok": ambiente.is_file(),
                "size": _human_bytes(ambiente.stat().st_size) if ambiente.is_file() else "-",
            },
        ],
        "status": _credenciais_status_read(),
        "archives": _credenciais_lista(config),
        "next_run": _credenciais_next_run(config),
        "timer": (saida or "").strip() or "desconhecido",
    }


def op_credenciais_backup_run(**_):
    return _credenciais_backup_run()


def op_credenciais_backup_verify(archive: str, **_):
    arquivo = _credenciais_arquivo(archive)
    config = _credenciais_config()
    estagio = Path(tempfile.mkdtemp(prefix=".verify-", dir=config["dir"]))
    try:
        _credenciais_extrair(arquivo, estagio)
        dados = _credenciais_conferir(estagio)
    finally:
        shutil.rmtree(estagio, ignore_errors=True)
    return {
        "archive": archive,
        "integrity": dados["integrity"],
        "hashes_ok": dados["hashes_ok"],
        "files": [item.get("arcname") for item in dados["manifest"].get("files", [])],
    }


def op_credenciais_backup_restore(archive: str, restart: bool = True, **_):
    arquivo = _credenciais_arquivo(archive)
    config = _credenciais_config()
    destino = Path(config["dir"])
    estagio = Path(tempfile.mkdtemp(prefix=".restore-", dir=destino))
    seguranca = destino / (
        "pre-restore-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    try:
        _credenciais_extrair(arquivo, estagio)
        dados = _credenciais_conferir(estagio)
        if str(dados["integrity"]).lower() != "ok":
            raise AgentError(
                f"Banco restaurado falhou na verificacao: {dados['integrity']}"
            )
        if not dados["hashes_ok"]:
            raise AgentError("O arquivo do backup nao confere com o manifesto")
        seguranca.mkdir(parents=True, exist_ok=True)
        os.chmod(seguranca, 0o700)
        banco = Path(config["db"])
        ambiente = Path(config["env"])
        if banco.is_file():
            shutil.copy2(banco, seguranca / "db.sqlite3")
        if ambiente.is_file():
            shutil.copy2(ambiente, seguranca / ".env")
        for item in dados["manifest"].get("files", []):
            alvo = banco if item.get("arcname") == "db.sqlite3" else ambiente
            shutil.copyfile(estagio / item["arcname"], alvo)
            try:
                os.chmod(alvo, int(item.get("mode") or 0o600) & 0o777)
                if hasattr(os, "chown"):
                    os.chown(alvo, int(item.get("uid", 0)), int(item.get("gid", 0)))
            except (OSError, NotImplementedError, ValueError):
                pass
    finally:
        shutil.rmtree(estagio, ignore_errors=True)
    reiniciado = False
    container = str(config.get("container") or "")
    if restart and re.match(r"^[A-Za-z0-9_.-]+$", container):
        # O container serve esta interface: reinicia depois da resposta.
        subprocess.Popen(
            ["sh", "-c", "sleep 3; docker restart \"$1\"", "sh", container],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        reiniciado = True
    _credenciais_status_write(
        {
            **_credenciais_status_read(),
            "last_restore": dt.datetime.now().isoformat(timespec="seconds"),
            "restored_archive": archive,
            "restore_ok": True,
            "restore_container": reiniciado,
            "pre_restore": seguranca.name,
        }
    )
    log(f"CREDENCIAIS_RESTORE {archive} docker={reiniciado}")
    return {
        "archive": archive,
        "integrity": dados["integrity"],
        "security_copy": str(seguranca),
        "restarted": reiniciado,
    }


def op_credenciais_backup_download(archive: str, **_):
    arquivo = _credenciais_arquivo(archive)
    _cleanup_downloads()
    token = dt.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
    pasta = Path(DOWNLOAD_DIR) / token
    pasta.mkdir(parents=True, exist_ok=False)
    os.chmod(pasta.parent, 0o700)
    os.chmod(pasta, 0o700)
    alvo = pasta / arquivo.name
    shutil.copyfile(arquivo, alvo)
    os.chmod(alvo, 0o600)
    raiz = Path(DATA_DIR).resolve()
    try:
        relativo = alvo.resolve().relative_to(raiz)
    except ValueError as exc:
        shutil.rmtree(pasta, ignore_errors=True)
        raise AgentError("DOWNLOAD_DIR fora de DATA_DIR") from exc
    return {
        "relative": str(relativo),
        "filename": arquivo.name,
        "size": alvo.stat().st_size,
    }


def _load_cold_config() -> dict:
    path = Path(COLD_CONFIG)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentError(f"Configuracao de copia fria invalida: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _save_cold_config(data: dict) -> None:
    path = Path(COLD_CONFIG)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _read_cold_status() -> dict:
    path = Path(COLD_STATUS)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cold_status(data: dict) -> None:
    path = Path(COLD_STATUS)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _primary_backup_disk() -> dict:
    config = _load_backup_config()
    disks = config.get("disks", [])
    if not disks:
        raise AgentError("Nenhum disco de backup primario configurado")
    return disks[0]


def _usb_disks(cold: dict) -> list[dict]:
    raw = run(
        [
            "lsblk",
            "-J",
            "-o",
            "NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,TRAN,RM,HOTPLUG",
        ]
    )
    data = json.loads(raw)
    disks = []

    def descendants(device: dict) -> list[dict]:
        result = []
        for child in device.get("children") or []:
            result.append(child)
            result.extend(descendants(child))
        return result

    for device in data.get("blockdevices", []):
        name = device.get("name", "")
        tran = (device.get("tran") or "").lower()
        rm = bool(device.get("rm"))
        hotplug = bool(device.get("hotplug"))
        if device.get("type") != "disk" or not (tran == "usb" or rm or hotplug):
            continue
        path = f"/dev/{name}"
        mounts = _collect_mounts(device)
        children = descendants(device)
        all_parts = [device] + children
        fstypes = [item.get("fstype") for item in all_parts if item.get("fstype")]
        labels = [item.get("label") for item in all_parts if item.get("label")]
        uuids = [item.get("uuid") for item in all_parts if item.get("uuid")]
        partitions = [f"/dev/{item['name']}" for item in children if item.get("name")]
        serial = (device.get("serial") or "").strip()
        model = (device.get("model") or "").strip()
        uuid = uuids[0] if uuids else None
        fstype = fstypes[0] if fstypes else None
        label = labels[0] if labels else None
        has_filesystem = bool(fstypes or uuids or children)
        configured = bool(
            cold
            and (
                (cold.get("serial") and cold.get("serial") == serial)
                or cold.get("device") == path
                or (cold.get("uuid") and cold.get("uuid") == uuid)
            )
        )
        system = any(mount == "/" for mount in mounts)
        if system:
            continue
        raid = any(item == "linux_raid_member" for item in fstypes)
        candidate = not system and not raid and not mounts
        reason = ""
        if system:
            reason = "disco do sistema"
        elif raid:
            reason = "membro de RAID"
        elif mounts:
            reason = "montado em " + ", ".join(mounts)
        if configured:
            required = f"RECONFIGURAR {path}"
        elif has_filesystem:
            required = f"APAGAR {path}"
        else:
            required = f"FORMATAR {path}"
        warnings = []
        if configured:
            warnings.append("Drive já configurado para copia fria")
        if has_filesystem:
            detail = f"Contém filesystem {fstype or 'desconhecido'}"
            if label:
                detail += f" (label {label})"
            warnings.append(detail)
        if not candidate:
            warnings.append(f"Indisponível: {reason}")
        disks.append(
            {
                "name": name,
                "path": path,
                "size": device.get("size"),
                "model": model,
                "serial": serial,
                "tran": device.get("tran"),
                "fstype": fstype,
                "label": label,
                "uuid": uuid,
                "partition": partitions[0] if partitions else None,
                "mounts": mounts,
                "has_filesystem": has_filesystem,
                "configured": configured,
                "candidate": candidate,
                "reason": reason,
                "required_phrase": required,
                "extra_confirmation": configured or has_filesystem,
                "warnings": warnings,
            }
        )
    return sorted(disks, key=lambda item: item["name"])


def op_cold_overview(**_):
    cold = _load_cold_config()
    primary = None
    primary_error = None
    try:
        primary = _primary_backup_disk()
    except AgentError as exc:
        primary_error = str(exc)
    return {
        "disks": _usb_disks(cold),
        "config": cold,
        "status": _read_cold_status(),
        "primary": primary,
        "primary_error": primary_error,
        "mount": COLD_MOUNT,
    }


def op_cold_prepare(
    device: str,
    label: str,
    confirmation: str,
    allow_existing: bool = False,
    **_,
):
    device = (device or "").strip()
    label = (label or "").strip().lower()
    confirmation = (confirmation or "").strip()
    if not BLOCK_DEVICE_RE.match(device):
        raise AgentError("Dispositivo USB invalido (use /dev/sdX, /dev/nvmeXnY ou similar)")
    if not COLD_LABEL_RE.match(label):
        raise AgentError("Label invalida (1-16 caracteres: a-z, 0-9, _ ou -)")
    primary = _primary_backup_disk()
    key_file = Path(primary.get("key_file") or "")
    if not key_file.is_file():
        raise AgentError("Senha do restic primario ausente")
    cold = _load_cold_config()
    disk = next((item for item in _usb_disks(cold) if item["path"] == device), None)
    if disk is None:
        raise AgentError(f"Disco USB nao encontrado: {device}")
    if not disk["candidate"]:
        raise AgentError(f"Disco USB indisponivel: {disk['reason']}")
    if disk["extra_confirmation"] and not allow_existing:
        raise AgentError("Confirmacao extra obrigatoria para drive nao vazio/configurado")
    if confirmation != disk["required_phrase"]:
        raise AgentError(
            f"Confirmacao incorreta. Digite exatamente: {disk['required_phrase']}"
        )
    if os.path.ismount(COLD_MOUNT):
        raise AgentError(f"{COLD_MOUNT} ja esta montado; ejetar antes")
    Path(COLD_MOUNT).mkdir(parents=True, exist_ok=True)
    run(["wipefs", "-a", device], timeout=60)
    run(
        [
            "parted",
            "-s",
            device,
            "mklabel",
            "gpt",
            "mkpart",
            "primary",
            "ext4",
            "1MiB",
            "100%",
        ],
        timeout=120,
    )
    run(["udevadm", "settle"], timeout=30)
    partition = f"{device}1"
    if not os.path.exists(partition):
        raise AgentError(f"Particao nao criada: {partition}")
    run(["mkfs.ext4", "-F", "-L", label, partition], timeout=600)
    run(["udevadm", "settle"], timeout=30)
    uuid = run(["blkid", "-s", "UUID", "-o", "value", partition]).strip()
    if not UUID_RE.match(uuid):
        raise AgentError(f"UUID invalido apos formatar: {uuid!r}")
    run(["mount", partition, COLD_MOUNT], timeout=60)
    repo = f"{COLD_MOUNT}/restic"
    Path(repo).mkdir(parents=True, exist_ok=True)
    os.chmod(repo, 0o700)
    run(
        ["restic", "-r", repo, "--password-file", str(key_file), "init"],
        timeout=300,
    )
    config = {
        "device": device,
        "partition": partition,
        "serial": disk.get("serial"),
        "uuid": uuid,
        "label": label,
        "mountpoint": COLD_MOUNT,
        "repo": repo,
        "key_file": str(key_file),
        "source_uuid": primary.get("uuid"),
        "configured_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    _save_cold_config(config)
    _write_cold_status(
        {"status": "prepared", "at": config["configured_at"], "message": "repo frio criado"}
    )
    log(f"COLD_PREPARE {device} {label} {uuid}")
    return config


def op_cold_copy(**_):
    cold = _load_cold_config()
    if not cold:
        raise AgentError("Nenhum drive de copia fria configurado")
    primary = _primary_backup_disk()
    key_file = Path(cold.get("key_file") or "")
    if not key_file.is_file():
        raise AgentError("Senha do restic frio ausente")
    disks = _usb_disks(cold)
    disk = next((item for item in disks if item.get("configured")), None)
    if disk is None:
        raise AgentError("Drive de copia fria nao conectado")
    if not Path("/etc/systemd/system/homelab-cold-copy.service").is_file():
        raise AgentError("Servico homelab-cold-copy ausente; rode sudo ./install-agent.sh")
    rc, _, _ = run_optional(
        ["systemctl", "is-active", "--quiet", "homelab-cold-copy.service"], timeout=10
    )
    if rc == 0:
        raise AgentError("Copia fria ja esta em execucao")
    run(["systemctl", "start", "--no-block", "homelab-cold-copy.service"], timeout=30)
    log(f"COLD_COPY_START {cold.get('device')}")
    return {"started": True, "device": cold.get("device")}


def op_cold_eject(**_):
    rc, _, _ = run_optional(
        ["systemctl", "is-active", "--quiet", "homelab-cold-copy.service"], timeout=10
    )
    if rc == 0:
        raise AgentError("Copia fria em execucao; aguarde terminar antes de ejetar")
    if os.path.ismount(COLD_MOUNT):
        run_optional(["sync"], timeout=60)
        run(["umount", COLD_MOUNT], timeout=60)
    return {"mounted": os.path.ismount(COLD_MOUNT), "mount": COLD_MOUNT}


def _read_net_dev() -> dict:
    data = {}
    try:
        lines = Path("/proc/net/dev").read_text().splitlines()[2:]
    except OSError:
        return data
    for line in lines:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        fields = rest.split()
        if name == "lo" or len(fields) < 16:
            continue
        try:
            data[name] = {"rx": int(fields[0]), "tx": int(fields[8])}
        except ValueError:
            continue
    return data


def _active_interface(interfaces: list[str]) -> str | None:
    rc, out, _ = run_optional(["ip", "route", "get", "1.1.1.1"], timeout=5)
    if rc == 0:
        match = re.search(r"\bdev\s+(\S+)", out)
        if match and match.group(1) in interfaces:
            return match.group(1)
    return interfaces[0] if interfaces else None


def _interface_details(name: str, rates: dict) -> dict:
    info = {
        "name": name,
        "state": "unknown",
        "speed_mbps": None,
        "link_rx_mbps": None,
        "link_tx_mbps": None,
        "signal_dbm": None,
        "ssid": None,
        "mac": None,
        **rates,
    }
    base = Path("/sys/class/net") / name
    try:
        info["state"] = (base / "operstate").read_text().strip()
    except OSError:
        pass
    try:
        info["mac"] = (base / "address").read_text().strip()
    except OSError:
        pass
    try:
        speed = int((base / "speed").read_text().strip())
        if speed > 0:
            info["speed_mbps"] = speed
    except (OSError, ValueError):
        pass
    if name.startswith("wlan"):
        rc, out, _ = run_optional(["iw", "dev", name, "link"], timeout=5)
        if rc == 0:
            ssid = re.search(r"SSID:\s*(.+)", out)
            signal = re.search(r"signal:\s*(-?\d+)", out)
            rx = re.search(r"rx bitrate:\s*([\d.]+)", out)
            tx = re.search(r"tx bitrate:\s*([\d.]+)", out)
            if ssid:
                info["ssid"] = ssid.group(1).strip()
            if signal:
                info["signal_dbm"] = int(signal.group(1))
            if rx:
                info["link_rx_mbps"] = round(float(rx.group(1)), 1)
            if tx:
                info["link_tx_mbps"] = round(float(tx.group(1)), 1)
    return info


def op_network_metrics(**_):
    first = _read_net_dev()
    started = time.monotonic()
    time.sleep(0.5)
    second = _read_net_dev()
    elapsed = max(0.1, time.monotonic() - started)
    names = sorted(set(first) & set(second))
    interfaces = []
    for name in names:
        delta_rx = max(0, second[name]["rx"] - first[name]["rx"])
        delta_tx = max(0, second[name]["tx"] - first[name]["tx"])
        rates = {
            "rx_mbps": round(delta_rx * 8 / 1_000_000 / elapsed, 1),
            "tx_mbps": round(delta_tx * 8 / 1_000_000 / elapsed, 1),
            "rx_mb_s": round(delta_rx / 1_000_000 / elapsed, 2),
            "tx_mb_s": round(delta_tx / 1_000_000 / elapsed, 2),
            "rx_total": second[name]["rx"],
            "tx_total": second[name]["tx"],
        }
        interfaces.append(_interface_details(name, rates))
    active_name = _active_interface(names)
    active = next((item for item in interfaces if item["name"] == active_name), None)
    return {
        "active": active,
        "interfaces": interfaces,
        "sampled_seconds": round(elapsed, 2),
    }


OPS = {
    "ping": op_ping,
    "host_capabilities": op_host_capabilities,
    "df": op_df,
    "list_users": op_list_users,
    "list_groups": op_list_groups,
    "create_group": op_create_group,
    "create_user": op_create_user,
    "set_password": op_set_password,
    "set_groups": op_set_groups,
    "toggle_user": op_toggle_user,
    "delete_user": op_delete_user,
    "delete_group": op_delete_group,
    "list_shares": op_list_shares,
    "create_share": op_create_share,
    "snapshot_usage": op_snapshot_usage,
    "snapshot_list": op_snapshot_list,
    "snapshot_create": op_snapshot_create,
    "snapshot_delete": op_snapshot_delete,
    "storage_overview": op_storage_overview,
    "live_metrics": op_live_metrics,
    "refresh_storage": op_refresh_storage,
    "storage_smart": op_storage_smart,
    "storage_smart_test": op_storage_smart_test,
    "backup_overview": op_backup_overview,
    "backup_snapshots": op_backup_snapshots,
    "backup_ls": op_backup_ls,
    "backup_search": op_backup_search,
    "backup_download": op_backup_download,
    "backup_disk_setup": op_backup_disk_setup,
    "backup_secret": op_backup_secret,
    "backup_job_save": op_backup_job_save,
    "backup_job_toggle": op_backup_job_toggle,
    "backup_job_delete": op_backup_job_delete,
    "backup_job_run": op_backup_job_run,
    "credenciais_backup_overview": op_credenciais_backup_overview,
    "credenciais_backup_run": op_credenciais_backup_run,
    "credenciais_backup_verify": op_credenciais_backup_verify,
    "credenciais_backup_restore": op_credenciais_backup_restore,
    "credenciais_backup_download": op_credenciais_backup_download,
    "cold_overview": op_cold_overview,
    "cold_prepare": op_cold_prepare,
    "cold_copy": op_cold_copy,
    "cold_eject": op_cold_eject,
    "network_metrics": op_network_metrics,
}


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(1024 * 1024).strip()
        if not raw:
            return
        try:
            request = json.loads(raw)
            op = request.pop("op", None)
            if op not in OPS:
                raise AgentError(f"Operacao desconhecida: {op}")
            data = OPS[op](**request)
            response = {"ok": True, "data": data}
        except AgentError as exc:
            response = {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log("ERROR " + traceback.format_exc().replace("\n", " | "))
            response = {"ok": False, "error": f"Erro interno: {exc}"}
        self.wfile.write(json.dumps(response).encode("utf-8") + b"\n")


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def main() -> int:
    if os.geteuid() != 0:
        print("O agente precisa rodar como root.", file=sys.stderr)
        return 1
    if len(sys.argv) > 1 and sys.argv[1] == "--credenciais-backup":
        try:
            dados = _credenciais_backup_run()
        except AgentError as exc:
            log("CREDENCIAIS_BACKUP_FAIL " + str(exc))
            print(str(exc), file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "archive": dados.get("archive"),
                    "size": dados.get("size"),
                    "removed": dados.get("removed"),
                }
            )
        )
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--collect":
        data = op_refresh_storage()
        print(
            json.dumps(
                {
                    "collected_at": data.get("collected_at"),
                    "disks": len(data.get("disks", [])),
                }
            )
        )
        return 0
    os.makedirs(CONFIG_DIR, exist_ok=True)
    load_policies()
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    server = Server(SOCKET_PATH, Handler)
    os.chmod(SOCKET_PATH, 0o660)
    log("AGENT START")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        log("AGENT STOP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
