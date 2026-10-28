from __future__ import annotations

import json
import os
from pathlib import Path


def test_usb_detection_lista_apenas_removiveis(agent_module, monkeypatch):
    dados = {
        "blockdevices": [
            {
                "name": "sda",
                "size": "1.8T",
                "type": "disk",
                "fstype": None,
                "tran": "sata",
                "rm": False,
                "mountpoints": ["/"],
                "children": [
                    {"name": "sda1", "fstype": "ext4", "mountpoints": ["/boot"]}
                ],
            },
            {
                "name": "sdb",
                "size": "32G",
                "type": "disk",
                "fstype": None,
                "tran": "usb",
                "rm": True,
                "mountpoints": [None],
                "children": [
                    {
                        "name": "sdb1",
                        "fstype": "ext4",
                        "label": "GITEA",
                        "mountpoints": [],
                    }
                ],
            },
        ]
    }
    monkeypatch.setattr(
        agent_module, "run", lambda *a, **k: json.dumps(dados)
    )
    disco = agent_module._gitea_usb_disks()
    assert [item["name"] for item in disco] == ["sdb"]
    assert disco[0]["has_filesystem"] is True
    assert disco[0]["label"] == "GITEA"
    assert disco[0]["fstype"] == "ext4"


def test_prune_mantem_apenas_os_ultimos(agent_module):
    pasta = Path(agent_module.GITEA_BACKUP_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in (
        "gitea-20260101-000000.zip",
        "gitea-20260102-000000.zip",
        "gitea-20260103-000000.zip",
    ):
        (pasta / nome).write_bytes(b"x")
    removidos = agent_module._gitea_prune()
    assert removidos == ["gitea-20260101-000000.zip"]
    assert len(agent_module._gitea_dumps()) == 2
    if os.name != "nt":
        assert (pasta / "gitea-20260103-000000.zip").is_file()
