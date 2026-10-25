from __future__ import annotations

import pytest

from .conftest import load_agent


@pytest.fixture
def agent(monkeypatch):
    return load_agent(
        monkeypatch,
        {
            "STORAGE_ROOT": "/mnt/nas",
            "SNAPSHOT_ROOT": "/mnt/nas/.snapshots",
            "ALLOWED_PATH_PREFIXES": "/mnt/nas/",
            "SNAPSHOT_BACKEND": "auto",
        },
    )


def test_capabilities_false_without_optional_tools(agent, monkeypatch):
    monkeypatch.setattr(agent.shutil, "which", lambda command: None)
    monkeypatch.setattr(agent, "detect_hwmon_fans", lambda: False)
    monkeypatch.setattr(agent, "_fstype", lambda path: "ext4")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: False)
    caps = agent.host_capabilities()
    assert caps["btrfs"] is False
    assert caps["restic"] is False
    assert caps["smartctl"] is False
    assert caps["hdparm"] is False
    assert caps["mdadm"] is False
    assert caps["hwmon_fans"] is False
    assert caps["storage_root_mounted"] is False
    assert caps["storage_root_fstype"] == "ext4"
    assert caps["snapshot_backend"] == "rsync"


def test_capabilities_true_with_tools(agent, monkeypatch):
    monkeypatch.setattr(agent.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(agent, "detect_hwmon_fans", lambda: True)
    monkeypatch.setattr(agent, "_fstype", lambda path: "btrfs")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: True)
    caps = agent.host_capabilities()
    assert all(caps[name] for name in ("btrfs", "restic", "smartctl", "hdparm", "mdadm"))
    assert caps["hwmon_fans"] is True
    assert caps["storage_root_mounted"] is True
    assert caps["storage_root_fstype"] == "btrfs"
    assert caps["snapshot_backend"] == "btrfs"


def test_smart_accepts_nvme_and_rejects_non_block(agent, monkeypatch):
    monkeypatch.setattr(agent.os.path, "exists", lambda path: True)
    monkeypatch.setattr(agent, "_disk_state", lambda path: "active")
    monkeypatch.setattr(agent, "_smart_summary", lambda path: {"health": "PASSED"})
    result = agent.op_storage_smart("/dev/nvme0n1")
    assert result["device"] == "/dev/nvme0n1"
    with pytest.raises(agent.AgentError):
        agent.op_storage_smart("/etc/passwd")


def test_ping_includes_capabilities(agent, monkeypatch):
    monkeypatch.setattr(agent, "host_capabilities", lambda: {"btrfs": True})
    assert agent.op_ping()["capabilities"] == {"btrfs": True}


def test_md_names_are_discovered_from_mdstat(agent):
    mdstat = "Personalities : [raid1]\nmd0 : active raid1 sda1[0]\n\nmd127 : active raid5 sdb1[0]\n"
    assert agent._md_names(mdstat) == ["md0", "md127"]


def test_backend_auto_and_explicit(agent, monkeypatch):
    monkeypatch.setattr(agent, "_fstype", lambda path: "btrfs")
    assert agent.snapshot_backend_for("/mnt/nas/docs", "auto") == "btrfs"
    monkeypatch.setattr(agent, "_fstype", lambda path: "ext4")
    assert agent.snapshot_backend_for("/mnt/nas/docs", "auto") == "rsync"
    assert agent.snapshot_backend_for("/mnt/nas/docs", "rsync") == "rsync"
    assert agent.snapshot_backend_for("/mnt/nas/docs", "none") == "none"
    assert agent.snapshot_backend_for("/mnt/nas/docs", "btrfs") == "none"
