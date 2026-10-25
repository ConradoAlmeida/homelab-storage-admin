from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ..conftest import load_agent
from .conftest import _run, lab_enabled

pytestmark = pytest.mark.lab


def _need(command: str):
    if not shutil.which(command):
        pytest.skip(f"{command} ausente")
    if not lab_enabled():
        pytest.skip("HOMELAB_LAB=1 e root sao necessarios")


def test_mdadm_raid1_with_loop_devices(loop_factory):
    _need("mdadm")
    one = loop_factory()
    two = loop_factory()
    name = f"homelab-lab-{os.getpid()}"
    md = f"/dev/md/{name}"
    try:
        _run(
            "mdadm",
            "--create",
            md,
            "--level=1",
            "--raid-devices=2",
            "--metadata=1.2",
            "--run",
            "--force",
            one,
            two,
        )
        _run("mdadm", "--wait", md, check=False)
        detail = _run("mdadm", "--detail", md).stdout
        assert "Raid Level : raid1" in detail
        assert "State : clean" in detail or "State : active" in detail
    finally:
        _run("mdadm", "--stop", md, check=False)
        for device in (one, two):
            _run("mdadm", "--zero-superblock", device, check=False)


def test_btrfs_subvolume_and_readonly_snapshot(loop_factory, mountpoint, mounted):
    _need("btrfs")
    _need("mkfs.btrfs")
    device = loop_factory(128)
    _run("mkfs.btrfs", "-f", device)
    mounted(device, mountpoint, "btrfs")
    sub = mountpoint / "docs"
    _run("btrfs", "subvolume", "create", str(sub))
    (sub / "file.txt").write_text("conteudo")
    snap = mountpoint / "snap"
    _run("btrfs", "subvolume", "snapshot", "-r", str(sub), str(snap))
    assert (snap / "file.txt").read_text() == "conteudo"
    _run("btrfs", "subvolume", "delete", str(snap))
    assert not snap.exists()


def test_agent_btrfs_share_and_snapshot(loop_factory, mountpoint, mounted, tmp_path, monkeypatch):
    _need("btrfs")
    _need("mkfs.btrfs")
    _need("testparm")
    device = loop_factory(160)
    _run("mkfs.btrfs", "-f", device)
    mounted(device, mountpoint, "btrfs")
    snaproot = mountpoint / ".snapshots"
    smb = tmp_path / "smb.conf"
    smb.write_text("[global]\n   workgroup = WORKGROUP\n")
    values = {
        "STORAGE_ROOT": str(mountpoint),
        "SNAPSHOT_ROOT": str(snaproot),
        "ALLOWED_PATH_PREFIXES": f"{mountpoint}/",
        "DF_MOUNTS": f"/,{mountpoint}",
        "SHARE_OWNER": "conrado",
        "SNAPSHOT_BACKEND": "btrfs",
        "SNAPSHOT_DENYLIST": "",
        "BACKUP_ROOT": str(tmp_path / "backup"),
        "AGENT_SOCKET": str(tmp_path / "agent.sock"),
        "SMB_CONF": str(smb),
        "CONFIG_DIR": str(tmp_path / "config"),
        "SNAP_CONFIG": str(tmp_path / "config" / "snapshots.json"),
        "LOG_FILE": str(tmp_path / "agent.log"),
    }
    agent = load_agent(monkeypatch, values)
    groups = ["labdocs", "labdocs_ro", "labdocs_rw"]
    try:
        share = mountpoint / "labdocs"
        result = agent.op_create_share("labdocs", str(share), snapshot=True, snapshot_keep=2)
        assert result["path"] == str(share)
        assert agent._fstype(str(share)) == "btrfs"
        created = agent.op_snapshot_create("labdocs")
        usage = agent.op_snapshot_usage()
        assert usage[0]["backend"] == "btrfs"
        assert usage[0]["count"] == 1
        assert (snaproot / "labdocs" / created["name"]).is_dir()
        agent.op_snapshot_delete("labdocs", created["name"])
        assert agent.op_snapshot_usage()[0]["count"] == 0
    finally:
        for group in groups:
            _run("groupdel", group, check=False)
