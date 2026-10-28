from __future__ import annotations

import getpass
import importlib.util
import os
import socketserver
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent" / "homelab-storage-agent.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

ENV_KEYS = (
    "SITE_NAME",
    "STORAGE_ROOT",
    "SNAPSHOT_ROOT",
    "ALLOWED_PATH_PREFIXES",
    "DF_MOUNTS",
    "SHARE_OWNER",
    "SNAPSHOT_DENYLIST",
    "SNAPSHOT_BACKEND",
    "BACKUP_ROOT",
    "JELLYFIN_ROOT",
    "AGENT_SOCKET",
    "AGENT_SOCKET_DIR",
    "BIND_ADDR",
    "BIND_PORT",
    "DATA_DIR",
    "DOWNLOAD_DIR",
    "SMB_CONF",
    "CONFIG_DIR",
    "SNAP_CONFIG",
    "BACKUP_CONFIG",
    "BACKUP_SECRETS",
    "BACKUP_STATUS_DIR",
    "COLD_CONFIG",
    "COLD_STATUS",
    "COLD_MOUNT",
    "CREDENCIAIS_CONFIG",
    "CREDENCIAIS_STATUS",
    "CREDENCIAIS_BACKUP_DIR",
    "CREDENCIAIS_DB",
    "CREDENCIAIS_ENV",
    "CREDENCIAIS_CONTAINER",
    "CREDENCIAIS_TIME",
    "CREDENCIAIS_RETENTION_DAYS",
    "LOG_FILE",
    "STORAGE_CACHE",
)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def set_env(monkeypatch, values: dict[str, str]) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))


def _stub_modules_ausentes_no_windows() -> None:
    """O agente importa grp/pwd e socketserver UNIX, que nao existem no Windows."""
    for nome in ("grp", "pwd"):
        if nome in sys.modules:
            continue
        try:
            __import__(nome)
        except ImportError:
            modulo = types.ModuleType(nome)
            if nome == "grp":
                def _ausente(*args, **kwargs):
                    raise KeyError(args[0] if args else "grupo")

                modulo.getgrall = lambda: []
                modulo.getgrnam = _ausente
                modulo.getgrgid = _ausente
            else:
                def _ausente_pwd(*args, **kwargs):
                    raise KeyError(args[0] if args else "usuario")

                modulo.getpwall = lambda: []
                modulo.getpwnam = _ausente_pwd
                modulo.getpwuid = _ausente_pwd
            sys.modules[nome] = modulo
    if not hasattr(socketserver, "ThreadingUnixStreamServer"):
        socketserver.ThreadingUnixStreamServer = socketserver.ThreadingTCPServer


def load_agent(monkeypatch, values: dict[str, str] | None = None):
    set_env(monkeypatch, values or {})
    _stub_modules_ausentes_no_windows()
    spec = importlib.util.spec_from_file_location(
        f"homelab_storage_agent_test_{os.getpid()}_{id(values)}",
        AGENT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def agent_module(monkeypatch, tmp_path):
    nas = tmp_path / "nas"
    nas.mkdir()
    snapshots = nas / ".snapshots"
    snapshots.mkdir()
    smb_conf = tmp_path / "smb.conf"
    smb_conf.write_text("[global]\n   workgroup = WORKGROUP\n")
    values = {
        "SITE_NAME": "Test Storage",
        "STORAGE_ROOT": str(nas),
        "SNAPSHOT_ROOT": str(snapshots),
        "ALLOWED_PATH_PREFIXES": f"{nas}/",
        "DF_MOUNTS": f"/,{nas}",
        "SHARE_OWNER": getpass.getuser(),
        "SNAPSHOT_DENYLIST": "",
        "SNAPSHOT_BACKEND": "rsync",
        "BACKUP_ROOT": str(tmp_path / "backup"),
        "AGENT_SOCKET": str(tmp_path / "agent.sock"),
        "AGENT_SOCKET_DIR": str(tmp_path),
        "BIND_ADDR": "127.0.0.1",
        "BIND_PORT": "8060",
        "DATA_DIR": str(tmp_path / "data"),
        "DOWNLOAD_DIR": str(tmp_path / "data" / "downloads"),
        "SMB_CONF": str(smb_conf),
        "CONFIG_DIR": str(tmp_path / "agent-config"),
        "SNAP_CONFIG": str(tmp_path / "agent-config" / "snapshots.json"),
        "BACKUP_CONFIG": str(tmp_path / "backup-config" / "config.json"),
        "BACKUP_SECRETS": str(tmp_path / "backup-config" / "secrets"),
        "BACKUP_STATUS_DIR": str(tmp_path / "backup-config" / "status"),
        "COLD_CONFIG": str(tmp_path / "backup-config" / "cold.json"),
        "COLD_STATUS": str(tmp_path / "backup-config" / "cold-status.json"),
        "COLD_MOUNT": str(tmp_path / "coldcopy"),
        "CREDENCIAIS_CONFIG": str(tmp_path / "backup-config" / "credenciais.json"),
        "CREDENCIAIS_STATUS": str(tmp_path / "backup-config" / "credenciais-status.json"),
        "CREDENCIAIS_BACKUP_DIR": str(tmp_path / "credenciais-backup"),
        "CREDENCIAIS_DB": str(tmp_path / "credenciais" / "db.sqlite3"),
        "CREDENCIAIS_ENV": str(tmp_path / "credenciais" / ".env"),
        "CREDENCIAIS_CONTAINER": "credenciais-teste",
        "CREDENCIAIS_TIME": "03:30",
        "CREDENCIAIS_RETENTION_DAYS": "30",
        "LOG_FILE": str(tmp_path / "agent.log"),
        "STORAGE_CACHE": str(tmp_path / "storage-cache.json"),
    }
    return load_agent(monkeypatch, values)


@pytest.fixture
def profile_env():
    return {
        name: parse_env_file(FIXTURES / f"host.env.{name}")
        for name in ("pi", "moya", "minimal")
    }
