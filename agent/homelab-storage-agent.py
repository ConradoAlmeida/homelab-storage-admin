#!/usr/bin/env python3
"""Agente privilegiado do Homelab Storage Admin.

Roda como root no host e expoe um Unix socket com operacoes validadas de
Samba, usuarios e snapshots. O app Django nunca executa shell direto.
"""
from __future__ import annotations

import configparser
import datetime as dt
import grp
import json
import os
import pwd
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import time
import traceback
from pathlib import Path

SOCKET_PATH = os.environ.get("SOCKET_PATH", "/run/homelab-storage-admin/agent.sock")
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
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/homelab-storage-agent.log")

USER_RE = re.compile(r"^[a-z][a-z0-9._-]{2,31}$")
SHARE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
GROUP_RE = re.compile(r"^[a-z][a-z0-9._-]{1,31}$")
SNAP_RE = re.compile(r"^@GMT-\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}$")
BACKUP_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
COLD_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{16,64}$")
JOB_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
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
DENY_SNAPSHOT = {
    s.strip() for s in os.environ.get("SNAPSHOT_DENYLIST", "").split(",") if s.strip()
}
RESERVED_SHARES = {"global", "homes", "printers", "print$"}

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


def op_storage_overview(**_):
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
        smart = _smart_summary(path) if name.startswith("sd") else {"state": "unavailable"}
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
    rc, out, _ = run_optional(["mdadm", "--detail", "/dev/md0"], timeout=10)
    raid["detail"] = out if rc == 0 else ""

    btrfs = {}
    rc, out, _ = run_optional(["btrfs", "filesystem", "usage", "--raw", "/mnt/nas"], timeout=15)
    btrfs["usage"] = out if rc == 0 else ""
    rc, out, _ = run_optional(["btrfs", "device", "stats", "/mnt/nas"], timeout=15)
    btrfs["stats"] = out if rc == 0 else ""
    rc, out, _ = run_optional(["btrfs", "scrub", "status", "-d", "/mnt/nas"], timeout=15)
    btrfs["scrub"] = out if rc == 0 else ""

    return {
        "system": _system_info(),
        "disks": disks,
        "raid": raid,
        "btrfs": btrfs,
    }


def op_storage_smart(device: str, **_):
    if not re.match(r"^/dev/sd[a-z]$", device or ""):
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
    if not re.match(r"^/dev/sd[a-z]$", device or ""):
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
    return {"pong": True, "agent": "homelab-storage-agent"}


def op_df(**_):
    mounts = list(DF_MOUNTS)
    backup_root = Path("/mnt/backup")
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


def op_list_shares(include_size=False, **_):
    parser = _parse_smb_conf()
    shares = []
    for section in parser.sections():
        if section.lower() == "global" or section.lower() in RESERVED_SHARES:
            continue
        if parser.getboolean(section, "printable", fallback=False):
            continue
        path = parser.get(section, "path", fallback="")
        item = {
            "name": section,
            "path": path,
            "comment": parser.get(section, "comment", fallback=""),
            "valid_users": parser.get(section, "valid users", fallback=""),
            "read_only": parser.getboolean(section, "read only", fallback=False),
            "write_list": parser.get(section, "write list", fallback=""),
            "force_group": parser.get(section, "force group", fallback=""),
            "browseable": parser.getboolean(section, "browseable", fallback=True),
        }
        if include_size:
            live = _dir_size_bytes(path, exclude=".snapshots")
            snapdir = os.path.join(SNAPSHOT_ROOT, section)
            item["size"] = live
            item["size_snapshots"] = _btrfs_du_bytes(snapdir)
            item["size_total"] = live + item["size_snapshots"]
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

    if not os.path.ismount(STORAGE_ROOT):
        raise AgentError(f"{STORAGE_ROOT} nao esta montado; monte o Btrfs antes de criar shares")
    if os.path.abspath(path) == os.path.abspath(STORAGE_ROOT):
        raise AgentError("Nao crie share na raiz do volume; use um subdiretorio/subvolume")
    if os.path.abspath(path).startswith(os.path.abspath(SNAPSHOT_ROOT) + os.sep):
        raise AgentError("Nao crie share dentro de .snapshots")

    parser = _parse_smb_conf()
    if parser.has_section(name):
        raise AgentError(f"Share ja existe: {name}")

    if snapshot:
        _ensure_subvolume(path)
        snapdir = os.path.join(SNAPSHOT_ROOT, name)
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
            f"    shadow:snapdir = {SNAPSHOT_ROOT}/{name}\n"
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
        policy[name] = {"path": path, "enabled": True, "keep": int(snapshot_keep or 7)}
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


def _snapshot_dir(share: str) -> tuple[str, str]:
    policy = load_policies()
    if share not in policy:
        raise AgentError(f"Share sem politica de snapshot: {share}")
    if share in DENY_SNAPSHOT:
        raise AgentError(f"Snapshot proibido para {share} (denylist)")
    if not policy[share].get("enabled"):
        raise AgentError(f"Politica de snapshot desativada para {share}")
    src = policy[share]["path"]
    if not os.path.ismount(STORAGE_ROOT):
        raise AgentError(f"{STORAGE_ROOT} nao esta montado; snapshots abortados")
    try:
        run(["btrfs", "subvolume", "show", src], timeout=10)
    except AgentError as exc:
        raise AgentError(
            f"{src} nao e um subvolume Btrfs; recrie o share com snapshot habilitado"
        ) from exc
    snapdir = os.path.join(SNAPSHOT_ROOT, share)
    os.makedirs(snapdir, exist_ok=True)
    os.chmod(snapdir, 0o755)
    return src, snapdir


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


def op_snapshot_usage(**_):
    policy = load_policies()
    result = []
    for share, cfg in sorted(policy.items()):
        src = cfg.get("path", "")
        enabled = bool(cfg.get("enabled"))
        snapdir = os.path.join(SNAPSHOT_ROOT, share) if src else ""
        # Nunca varre share desativado.
        names = _snapshot_list(snapdir) if (enabled and snapdir) else []
        # Btrfs compartilha extents entre snapshots; o numero e aproximado.
        total_size = _btrfs_du_bytes(snapdir) if (enabled and snapdir) else 0
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
                "snapshots": snapshots,
            }
        )
    return result


def op_snapshot_list(share: str, **_):
    _, snapdir = _snapshot_dir(share)
    return {"share": share, "snapshots": _snapshot_list(snapdir)}


def op_snapshot_create(share: str, **_):
    src, snapdir = _snapshot_dir(share)
    names = _snapshot_list(snapdir)
    stamp = dt.datetime.now().strftime("@GMT-%Y.%m.%d-%H.%M.%S")
    dest = os.path.join(snapdir, stamp)
    if os.path.exists(dest):
        raise AgentError(f"Snapshot ja existe: {stamp}")

    try:
        run(["btrfs", "subvolume", "snapshot", "-r", src, dest], timeout=1800)
    except AgentError:
        _btrfs_delete(dest)
        raise

    keep = max(1, int(load_policies()[share].get("keep", 7)))
    names = _snapshot_list(snapdir)
    for old in names[: max(0, len(names) - keep)]:
        _btrfs_delete(os.path.join(snapdir, old))
        log(f"PRUNE {share}/{old}")
    log(f"SNAPSHOT {share} {stamp}")
    return {"share": share, "name": stamp}


def op_snapshot_delete(share: str, name: str, **_):
    if not SNAP_RE.match(name or ""):
        raise AgentError("Nome de snapshot invalido")
    _, snapdir = _snapshot_dir(share)
    target = os.path.join(snapdir, name)
    real = os.path.realpath(target)
    if os.path.dirname(real) != os.path.realpath(snapdir):
        raise AgentError("Caminho de snapshot invalido")
    if not os.path.isdir(real):
        raise AgentError(f"Snapshot nao encontrado: {name}")
    _btrfs_delete(real)
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
        system = name.startswith("mmcblk") or any(
            mount == "/" or mount.startswith("/boot") for mount in mounts
        )
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
    if not re.match(r"^/dev/sd[a-z]$", device):
        raise AgentError("Dispositivo invalido (use /dev/sdX)")
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
        system = name.startswith("mmcblk") or any(
            mount == "/" or mount.startswith("/boot") for mount in mounts
        )
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
    if not re.match(r"^/dev/sd[a-z]$", device):
        raise AgentError("Dispositivo USB invalido (use /dev/sdX)")
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
    "df": op_df,
    "list_users": op_list_users,
    "list_groups": op_list_groups,
    "create_user": op_create_user,
    "set_password": op_set_password,
    "set_groups": op_set_groups,
    "toggle_user": op_toggle_user,
    "list_shares": op_list_shares,
    "create_share": op_create_share,
    "snapshot_usage": op_snapshot_usage,
    "snapshot_list": op_snapshot_list,
    "snapshot_create": op_snapshot_create,
    "snapshot_delete": op_snapshot_delete,
    "storage_overview": op_storage_overview,
    "storage_smart": op_storage_smart,
    "storage_smart_test": op_storage_smart_test,
    "backup_overview": op_backup_overview,
    "backup_disk_setup": op_backup_disk_setup,
    "backup_secret": op_backup_secret,
    "backup_job_save": op_backup_job_save,
    "backup_job_toggle": op_backup_job_toggle,
    "backup_job_delete": op_backup_job_delete,
    "backup_job_run": op_backup_job_run,
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
