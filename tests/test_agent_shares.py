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
        if args[:3] == ["btrfs", "subvolume", "create"]:
            os.makedirs(args[3], exist_ok=True)
        return ""

    monkeypatch.setattr(agent, "run", fake_run)
    return commands


def test_create_share_btrfs_sem_politica_cria_subvolume(agent_module, monkeypatch):
    agent = agent_module
    commands = prepare(agent, monkeypatch)
    agent.SNAPSHOT_BACKEND = "btrfs"
    monkeypatch.setattr(agent, "_fstype", lambda path: "btrfs")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: True)
    path = Path(agent.STORAGE_ROOT) / "docs"
    result = agent.op_create_share("docs", str(path), snapshot=False)
    assert result["path"] == str(path)
    assert any(cmd[:3] == ["btrfs", "subvolume", "create"] for cmd in commands)
    assert "docs" not in agent.load_policies()
    texto = Path(agent.SMB_CONF).read_text()
    assert "shadow:" not in texto


def test_create_share_btrfs_desmontado_sem_snapshot_recusa(agent_module, monkeypatch):
    agent = agent_module
    prepare(agent, monkeypatch)
    agent.SNAPSHOT_BACKEND = "btrfs"
    monkeypatch.setattr(agent, "_fstype", lambda path: "btrfs")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: False)
    path = Path(agent.STORAGE_ROOT) / "docs"
    with pytest.raises(agent.AgentError, match="montado"):
        agent.op_create_share("docs", str(path), snapshot=False)
    assert not path.exists()


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


def test_dir_size_reaproveita_medicao_por_tres_minutos(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    calls = {"n": 0}

    def fake_run(args, input_text=None, timeout=60):
        calls["n"] += 1
        return "10\t" + args[-1]

    monkeypatch.setattr(agent, "run", fake_run)
    agent._size_cache.clear()
    path = str(tmp_path)
    assert agent._dir_size_bytes(path) == 10
    assert agent._dir_size_bytes(path) == 10
    assert calls["n"] == 1
    agent._forget_size_cache()
    assert agent._dir_size_bytes(path) == 10
    assert calls["n"] == 2


def test_share_sizes_responde_enquanto_mede(agent_module):
    agent = agent_module
    previous = (
        agent._share_sizes_running,
        agent._share_sizes_ready,
        agent._share_sizes_error,
    )
    agent._share_sizes_running = True
    agent._share_sizes_ready = None
    agent._share_sizes_error = ""
    try:
        data = agent.op_share_sizes()
    finally:
        (
            agent._share_sizes_running,
            agent._share_sizes_ready,
            agent._share_sizes_error,
        ) = previous
    assert data["pending"] is True
    assert data["shares"] == []


def test_dir_size_nao_grava_falha_no_cache(agent_module, monkeypatch, tmp_path):
    agent = agent_module

    def boom(args, input_text=None, timeout=60):
        raise agent.AgentError("du falhou")

    monkeypatch.setattr(agent, "run", boom)
    agent._size_cache.clear()
    assert agent._dir_size_bytes(str(tmp_path)) == 0
    assert agent._size_cache == {}
