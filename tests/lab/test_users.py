from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from ..conftest import load_agent
from .conftest import lab_enabled

pytestmark = pytest.mark.lab


def _need_lab():
    if not lab_enabled():
        pytest.skip("HOMELAB_LAB=1 e root sao necessarios")
    for comando in ("useradd", "userdel", "smbpasswd"):
        if not shutil.which(comando):
            pytest.skip(f"{comando} ausente")


def _smb_login(username: str, password: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "smbclient",
            "-L",
            "127.0.0.1",
            f"-U{username}%{password}",
            "-m",
            "SMB3",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _smb_auth_ok(result: subprocess.CompletedProcess) -> bool:
    texto = f"{result.stdout}\n{result.stderr}"
    if "NT_STATUS_LOGON_FAILURE" in texto or "NT_STATUS_ACCESS_DENIED" in texto:
        return False
    return result.returncode == 0


def test_set_password_real(monkeypatch):
    _need_lab()
    username = f"labpw{os.getpid()}"
    antiga = "senhantiga1"
    nova = "senhanova12"
    agent = load_agent(
        monkeypatch,
        {
            "STORAGE_ROOT": "/tmp",
            "SNAPSHOT_ROOT": "/tmp/.snapshots",
            "ALLOWED_PATH_PREFIXES": "/tmp/",
            "SNAPSHOT_BACKEND": "none",
            "CONFIG_DIR": f"/tmp/{username}-config",
            "SNAP_CONFIG": f"/tmp/{username}-config/snapshots.json",
            "LOG_FILE": f"/tmp/{username}.log",
            "SHARE_OWNER": "conrado",
        },
    )
    try:
        criado = agent.op_create_user(username, antiga, [])
        assert criado["username"] == username
        trocado = agent.op_set_password(username, nova)
        assert trocado["username"] == username
        with pytest.raises(agent.AgentError, match="Usuario nao existe"):
            agent.op_set_password("zzznope", nova)
        if shutil.which("smbclient"):
            assert _smb_auth_ok(_smb_login(username, nova))
            assert not _smb_auth_ok(_smb_login(username, antiga))
    finally:
        subprocess.run(["smbpasswd", "-x", username], check=False, capture_output=True)
        subprocess.run(["userdel", "-r", username], check=False, capture_output=True)
