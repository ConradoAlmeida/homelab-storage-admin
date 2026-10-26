from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("rsync") is None,
    reason="rsync nao esta no PATH",
)


def test_checksum_task_runs_and_reports_success(agent_module):
    agent = agent_module
    source = Path(agent.STORAGE_ROOT) / "source"
    dest = Path(agent.STORAGE_ROOT) / "dest"
    source.mkdir()
    dest.mkdir()
    (source / "a.txt").write_text("same")
    (dest / "a.txt").write_text("same")

    task = agent.op_task_start("checksum", str(source), str(dest))
    for _ in range(50):
        current = agent.op_task_status(task["id"])
        if current["status"] != "running":
            break
        time.sleep(0.1)
    assert current["status"] == "success"
    assert current["returncode"] == 0
    assert agent.op_task_list()[0]["id"] == task["id"]


def test_checksum_task_rejects_invalid_kind_and_paths(agent_module):
    agent = agent_module
    source = Path(agent.STORAGE_ROOT) / "source"
    dest = Path(agent.STORAGE_ROOT) / "dest"
    source.mkdir()
    dest.mkdir()
    with pytest.raises(agent.AgentError, match="Tipo"):
        agent.op_task_start("copy", str(source), str(dest))
    with pytest.raises(agent.AgentError, match="fora"):
        agent.op_task_start("checksum", "/etc", str(dest))
