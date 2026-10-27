from __future__ import annotations

import json
from pathlib import Path


def test_backup_snapshots_parses_restic_json(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    key = tmp_path / "key"
    key.write_text("secret")
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        agent,
        "_load_backup_config",
        lambda: {
            "disks": [
                {
                    "label": "hdd700",
                    "uuid": "u1",
                    "repo": str(repo),
                    "key_file": str(key),
                }
            ],
            "jobs": [],
        },
    )
    monkeypatch.setattr(agent.shutil, "which", lambda command: "/usr/bin/restic")
    payload = [
        {
            "id": "a" * 64,
            "short_id": "aaaaaaaa",
            "time": "2026-10-26T22:15:24-03:00",
            "hostname": "homelab",
            "paths": ["/mnt/nas/casa"],
            "tags": ["homelab"],
            "summary": {
                "total_files_processed": 10,
                "total_bytes_processed": 1234,
                "data_added_packed": 50,
            },
        }
    ]
    monkeypatch.setattr(agent, "run", lambda *args, **kwargs: json.dumps(payload))
    data = agent.op_backup_snapshots()
    assert data["errors"] == []
    assert data["snapshots"][0]["disk_label"] == "hdd700"
    assert data["snapshots"][0]["files"] == 10
    assert data["snapshots"][0]["bytes"] == 1234
    assert data["snapshots"][0]["empty"] is False
