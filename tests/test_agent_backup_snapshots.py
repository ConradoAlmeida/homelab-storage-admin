from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


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
    assert data["snapshots"][0]["browse_path"] == "/mnt/nas/casa"
    assert data["snapshots"][0]["empty"] is False


def _backup_config(agent_module, monkeypatch, tmp_path):
    key = tmp_path / "key"
    key.write_text("secret")
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        agent_module,
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
    monkeypatch.setattr(
        agent_module.shutil, "which", lambda command: "/usr/bin/restic"
    )


def test_backup_ls_lists_immediate_children(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    _backup_config(agent, monkeypatch, tmp_path)
    lines = [
        {
            "message_type": "snapshot",
            "id": "a" * 64,
            "short_id": "aaaaaaaa",
            "time": "2026-10-26T22:15:24-03:00",
            "hostname": "homelab",
            "paths": ["/mnt/nas"],
            "tags": ["homelab"],
        },
        {"message_type": "node", "name": "nas", "path": "/mnt/nas", "type": "dir"},
        {
            "message_type": "node",
            "name": "casa",
            "path": "/mnt/nas/casa",
            "type": "dir",
            "mtime": "2026-10-25T22:37:27-03:00",
            "permissions": "drwxrwxr-x",
        },
        {
            "message_type": "node",
            "name": "a.txt",
            "path": "/mnt/nas/casa/a.txt",
            "type": "file",
            "size": 12,
        },
        {
            "message_type": "node",
            "name": "documentos",
            "path": "/mnt/nas/documentos",
            "type": "dir",
        },
    ]
    monkeypatch.setattr(
        agent,
        "run",
        lambda *args, **kwargs: "\n".join(json.dumps(line) for line in lines),
    )
    data = agent.op_backup_ls("u1", "aaaaaaaa", "/mnt/nas")
    assert data["snapshot"]["short_id"] == "aaaaaaaa"
    assert [entry["name"] for entry in data["entries"]] == ["casa", "documentos"]
    assert data["entries"][0]["size"] is None
    assert data["entries"][0]["mtime"] == "2026-10-25T22:37:27-03:00"


def test_backup_ls_rejects_traversal(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    _backup_config(agent, monkeypatch, tmp_path)
    try:
        agent.op_backup_ls("u1", "aaaaaaaa", "/mnt/nas/../etc")
    except agent.AgentError as exc:
        assert "invalido" in str(exc)
    else:
        raise AssertionError("path traversal deveria falhar")


def test_backup_search_wraps_plain_query(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    _backup_config(agent, monkeypatch, tmp_path)
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return json.dumps(
            [
                {
                    "snapshot": "a" * 64,
                    "hits": 1,
                    "matches": [
                        {
                            "path": "/mnt/nas/casa/README.md",
                            "type": "file",
                            "size": 12,
                            "mtime": "2026-10-25T22:37:27-03:00",
                            "permissions": "-rw-r--r--",
                        }
                    ],
                }
            ]
        )

    monkeypatch.setattr(agent, "run", fake_run)
    data = agent.op_backup_search("u1", "aaaaaaaa", "README")
    assert seen["args"][-1] == "*README*"
    assert data["pattern"] == "*README*"
    assert data["total"] == 1
    assert data["matches"][0]["name"] == "README.md"
    assert data["matches"][0]["parent"] == "/mnt/nas/casa"


def test_backup_search_keeps_glob_and_limits(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    _backup_config(agent, monkeypatch, tmp_path)
    matches = [
        {"path": f"/mnt/nas/casa/{index}.pdf", "type": "file", "size": index}
        for index in range(3)
    ]
    monkeypatch.setattr(
        agent,
        "run",
        lambda *args, **kwargs: json.dumps(
            [{"snapshot": "a" * 64, "hits": 3, "matches": matches}]
        ),
    )
    data = agent.op_backup_search("u1", "aaaaaaaa", "*.pdf", limit=2)
    assert data["pattern"] == "*.pdf"
    assert data["total"] == 3
    assert data["truncated"] is True
    assert len(data["matches"]) == 2


def test_backup_download_writes_shared_file(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    _backup_config(agent, monkeypatch, tmp_path)

    def fake_run(args, stdout=None, stderr=None, timeout=None, check=False):
        stdout.write(b"conteudo")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    result = agent.op_backup_download("u1", "aaaaaaaa", "/mnt/nas/casa/a.txt")
    target = Path(agent.DATA_DIR) / result["relative"]
    assert target.read_bytes() == b"conteudo"
    assert result["filename"] == "a.txt"
    assert result["size"] == 8


def test_backup_download_rejects_traversal(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    _backup_config(agent, monkeypatch, tmp_path)
    try:
        agent.op_backup_download("u1", "aaaaaaaa", "/mnt/nas/../etc/passwd")
    except agent.AgentError as exc:
        assert "invalido" in str(exc)
    else:
        raise AssertionError("path traversal deveria falhar")
