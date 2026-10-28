from __future__ import annotations

import configparser
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="caminhos POSIX do servidor Linux",
)


def empty_smb():
    return configparser.ConfigParser()


def prepare(agent, monkeypatch):
    monkeypatch.setattr(agent, "_parse_smb_conf", empty_smb)
    monkeypatch.setattr(agent, "_ensure_group", lambda name: None)
    monkeypatch.setattr(agent, "_user_exists", lambda name: False)
    monkeypatch.setattr(agent.shutil, "chown", lambda *args, **kwargs: None)
    commands = []

    def fake_run(args, input_text=None, timeout=60):
        commands.append(list(args))
        return ""

    monkeypatch.setattr(agent, "run", fake_run)
    return commands


def test_create_share_without_snapshot_does_not_need_storage_mount(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    commands = prepare(agent, monkeypatch)
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: False)
    monkeypatch.setattr(
        agent,
        "_ensure_subvolume",
        lambda path: pytest.fail("nao deve chamar btrfs para share sem snapshot"),
    )
    path = Path(agent.STORAGE_ROOT) / "docs"
    result = agent.op_create_share("docs", str(path), snapshot=False)
    assert result["path"] == str(path)
    assert path.is_dir()
    assert all("btrfs" not in " ".join(command) for command in commands)


def test_create_share_with_rsync_snapshot(agent_module, monkeypatch):
    agent = agent_module
    commands = prepare(agent, monkeypatch)
    monkeypatch.setattr(agent.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(
        agent,
        "_ensure_subvolume",
        lambda path: pytest.fail("backend rsync nao deve chamar btrfs"),
    )
    path = Path(agent.STORAGE_ROOT) / "docs"
    result = agent.op_create_share(
        "docs", str(path), snapshot=True, snapshot_keep=5
    )
    snapdir = path / ".snapshots"
    assert snapdir.is_dir()
    assert result["path"] == str(path)
    assert all("btrfs" not in " ".join(command) for command in commands)
    policy = agent.load_policies()
    assert policy["docs"]["backend"] == "rsync"
    assert policy["docs"]["snapdir"] == str(snapdir)
    assert "shadow:snapdir = " + str(snapdir) in Path(agent.SMB_CONF).read_text()


def test_denylist_blocks_snapshot_before_any_operation(agent_module, monkeypatch):
    agent = agent_module
    agent.DENY_SNAPSHOT = {"Veronte_Images"}
    path = Path(agent.STORAGE_ROOT) / "Veronte_Images"
    with pytest.raises(agent.AgentError, match="denylist"):
        agent.op_create_share("Veronte_Images", str(path), snapshot=True)


def test_denylisted_share_does_not_expose_snapdir(agent_module, monkeypatch):
    agent = agent_module
    agent.DENY_SNAPSHOT = {"Veronte_Images"}
    parser = configparser.ConfigParser()
    parser.read_string(
        "[Veronte_Images]\n"
        "path = " + str(Path(agent.STORAGE_ROOT) / "Veronte_Images") + "\n"
    )
    monkeypatch.setattr(agent, "_parse_smb_conf", lambda: parser)
    shares = agent.op_list_shares(include_size=False)
    assert shares[0]["backend"] == "none"
    assert shares[0]["snapdir"] == ""


def test_list_shares_returns_backend_and_snapdir(agent_module, monkeypatch):
    agent = agent_module
    parser = configparser.ConfigParser()
    parser.read_string(
        "[docs]\n"
        "path = " + str(Path(agent.STORAGE_ROOT) / "docs") + "\n"
    )
    monkeypatch.setattr(agent, "_parse_smb_conf", lambda: parser)
    shares = agent.op_list_shares(include_size=False)
    assert shares[0]["backend"] == "rsync"
    assert shares[0]["snapdir"].endswith("/docs/.snapshots")


def test_list_shares_size_payload_has_live_extra_total(agent_module, monkeypatch):
    agent = agent_module
    parser = configparser.ConfigParser()
    parser.read_string(
        "[docs]\n"
        "path = " + str(Path(agent.STORAGE_ROOT) / "docs") + "\n"
    )
    monkeypatch.setattr(agent, "_parse_smb_conf", lambda: parser)
    monkeypatch.setattr(
        agent,
        "_dir_size_bytes",
        lambda path, exclude=None: 100 if exclude == ".snapshots" else 250,
    )
    monkeypatch.setattr(agent, "_snapshot_extra_bytes", lambda path, snapdir: 150)
    shares = agent.op_list_shares(include_size=True)
    assert shares[0]["size"] == 100
    assert shares[0]["size_snapshots"] == 150
    assert shares[0]["size_total"] == 250
