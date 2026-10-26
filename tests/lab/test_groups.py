from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from ..conftest import load_agent
from .conftest import lab_enabled

pytestmark = pytest.mark.lab


def test_create_group_real(monkeypatch):
    if not lab_enabled():
        pytest.skip("HOMELAB_LAB=1 e root sao necessarios")
    if not shutil.which("groupadd") or not shutil.which("groupdel"):
        pytest.skip("groupadd/groupdel ausentes")

    name = f"labgrp{os.getpid()}"
    agent = load_agent(
        monkeypatch,
        {
            "STORAGE_ROOT": "/tmp",
            "SNAPSHOT_ROOT": "/tmp/.snapshots",
            "ALLOWED_PATH_PREFIXES": "/tmp/",
            "SNAPSHOT_BACKEND": "none",
            "CONFIG_DIR": f"/tmp/{name}-config",
            "SNAP_CONFIG": f"/tmp/{name}-config/snapshots.json",
            "LOG_FILE": f"/tmp/{name}.log",
        },
    )
    try:
        result = agent.op_create_group(name)
        assert result["name"] == name
        assert subprocess.run(
            ["getent", "group", name], check=False, capture_output=True
        ).returncode == 0
    finally:
        subprocess.run(["groupdel", name], check=False, capture_output=True)
