from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("rsync") is None,
    reason="rsync nao esta no PATH",
)


def policy(agent, keep=5):
    share = Path(agent.STORAGE_ROOT) / "docs"
    share.mkdir(parents=True, exist_ok=True)
    snapdir = share / ".snapshots"
    agent.save_policies(
        {
            "docs": {
                "path": str(share),
                "enabled": True,
                "keep": keep,
                "backend": "rsync",
                "snapdir": str(snapdir),
            }
        }
    )
    return share, snapdir


def test_rsync_snapshot_uses_hardlink_for_unchanged_file(agent_module):
    agent = agent_module
    share, snapdir = policy(agent)
    (share / "unchanged.txt").write_text("same")
    first = agent.op_snapshot_create("docs")["name"]
    time.sleep(1.1)
    (share / "changed.txt").write_text("new")
    second = agent.op_snapshot_create("docs")["name"]
    assert first != second
    assert (snapdir / first / "unchanged.txt").is_file()
    assert (snapdir / second / "changed.txt").is_file()
    assert (
        (snapdir / first / "unchanged.txt").stat().st_ino
        == (snapdir / second / "unchanged.txt").stat().st_ino
    )


def test_rsync_snapshot_delete_only_named_snapshot(agent_module):
    agent = agent_module
    share, snapdir = policy(agent)
    (share / "a.txt").write_text("a")
    first = agent.op_snapshot_create("docs")["name"]
    time.sleep(1.1)
    second = agent.op_snapshot_create("docs")["name"]
    agent.op_snapshot_delete("docs", first)
    assert not (snapdir / first).exists()
    assert (snapdir / second).is_dir()


def test_rsync_prune_respects_keep(agent_module):
    agent = agent_module
    share, snapdir = policy(agent, keep=1)
    (share / "a.txt").write_text("a")
    first = agent.op_snapshot_create("docs")["name"]
    time.sleep(1.1)
    second = agent.op_snapshot_create("docs")["name"]
    names = [item.name for item in snapdir.iterdir() if item.is_dir()]
    assert first not in names
    assert second in names
    assert len(names) == 1


def test_snapshot_list_and_usage_report_backend_and_size(agent_module):
    agent = agent_module
    share, snapdir = policy(agent)
    (share / "old-only.txt").write_text("old")
    first = agent.op_snapshot_create("docs")["name"]
    (share / "old-only.txt").unlink()
    (share / "live.txt").write_text("live")
    time.sleep(1.1)
    agent.op_snapshot_create("docs")
    listed = agent.op_snapshot_list("docs")
    assert listed["backend"] == "rsync"
    assert listed["snapdir"] == str(snapdir)
    usage = agent.op_snapshot_usage()
    assert usage[0]["backend"] == "rsync"
    assert usage[0]["count"] == 2
    assert usage[0]["size"] >= len("old")


def test_snapshot_delete_rejects_traversal(agent_module):
    agent = agent_module
    policy(agent)
    with pytest.raises(agent.AgentError):
        agent.op_snapshot_delete("docs", "../fora")
