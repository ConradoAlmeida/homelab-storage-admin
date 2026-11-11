from __future__ import annotations


def test_storage_overview_uses_cache_and_force_refreshes(agent_module, monkeypatch):
    agent = agent_module
    calls = []

    def collect():
        calls.append(len(calls) + 1)
        return {"marker": calls[-1], "disks": []}

    monkeypatch.setattr(agent, "_collect_storage_overview", collect)

    first = agent.op_storage_overview()
    assert first["marker"] == 1
    assert first["cache_age_seconds"] == 0
    assert first["stale"] is False

    second = agent.op_storage_overview()
    assert second["marker"] == 1
    assert calls == [1]

    forced = agent.op_storage_overview(force=True)
    assert forced["marker"] == 2
    assert calls == [1, 2]


def test_mdstat_e_relido_mesmo_com_cache_de_disco(agent_module, monkeypatch):
    agent = agent_module
    leituras = []

    def collect():
        return {"disks": [{"name": "sda"}], "raid": {"mdstat": "velho", "detail": ""}}

    def raid_now():
        leituras.append(1)
        return {"mdstat": "resync = 32.0%", "detail": ""}

    monkeypatch.setattr(agent, "_collect_storage_overview", collect)
    monkeypatch.setattr(agent, "_raid_now", raid_now)
    agent.op_storage_overview()
    segunda = agent.op_storage_overview()
    assert segunda["disks"] == [{"name": "sda", "parts": []}]
    assert segunda["raid"]["mdstat"] == "resync = 32.0%"
    assert len(leituras) == 2


def _noe_seagate() -> dict:
    return {
        "name": "sda",
        "type": "disk",
        "children": [
            {
                "name": "sda1",
                "type": "part",
                "size": "512M",
                "fstype": "vfat",
                "mountpoints": ["/boot/efi"],
            },
            {
                "name": "sda2",
                "type": "part",
                "size": "2G",
                "fstype": "ext4",
                "mountpoints": ["/boot"],
            },
            {
                "name": "sda3",
                "type": "part",
                "size": "1.8T",
                "fstype": "LVM2_member",
                "mountpoints": [None],
                "children": [
                    {
                        "name": "ubuntu-lv",
                        "type": "lvm",
                        "size": "200G",
                        "fstype": "ext4",
                        "mountpoints": ["/"],
                    },
                    {
                        "name": "data-lv",
                        "type": "lvm",
                        "size": "1.5T",
                        "fstype": "ext4",
                        "mountpoints": ["/mnt/backup"],
                    },
                ],
            },
        ],
    }


def _noe_wd_raid() -> dict:
    return {
        "name": "sdb",
        "type": "disk",
        "children": [
            {
                "name": "sdb1",
                "type": "part",
                "size": "4T",
                "fstype": "linux_raid_member",
                "mountpoints": [None],
                "children": [
                    {
                        "name": "md0",
                        "type": "raid1",
                        "size": "4T",
                        "fstype": "ext4",
                        "mountpoints": ["/mnt/data"],
                    }
                ],
            }
        ],
    }


def test_disk_parts_seagate(agent_module):
    parts = agent_module._disk_parts(_noe_seagate())
    assert [p["name"] for p in parts] == ["sda1", "sda2", "ubuntu-lv", "data-lv"]
    backup = next(p for p in parts if p["name"] == "data-lv")
    assert backup["mounts"] == ["/mnt/backup"]
    assert "sda3" not in {p["name"] for p in parts}


def test_disk_parts_wd_raid(agent_module):
    parts = agent_module._disk_parts(_noe_wd_raid())
    assert [p["name"] for p in parts] == ["sdb1", "md0"]
    assert parts[0]["fstype"] == "linux_raid_member"
    assert parts[1]["mounts"] == ["/mnt/data"]


def test_storage_overview_atualiza_uso_sem_recoletar(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    monkeypatch.setattr(agent, "STORAGE_CACHE", str(tmp_path / "storage.json"))
    coletas = []
    smart_chamadas = []

    def collect():
        coletas.append(1)
        smart_chamadas.append(1)
        return {
            "disks": [
                {
                    "name": "sda",
                    "parts": [
                        {
                            "name": "ubuntu-lv",
                            "size": "200G",
                            "fstype": "ext4",
                            "mounts": ["/"],
                            "usage": None,
                        }
                    ],
                }
            ],
            "raid": {"mdstat": "", "detail": ""},
            "btrfs": {},
            "system": {},
        }

    medidas = [{"total": 1_000, "used": 400, "free": 600}]

    def disk_usage(_mount):
        u = medidas[0]

        class Uso:
            total = u["total"]
            used = u["used"]
            free = u["free"]

        return Uso()

    monkeypatch.setattr(agent, "_collect_storage_overview", collect)
    monkeypatch.setattr(agent.shutil, "disk_usage", disk_usage)
    monkeypatch.setattr(agent.os.path, "ismount", lambda _m: True)

    primeira = agent.op_storage_overview()
    assert primeira["disks"][0]["parts"][0]["usages"][0]["total"] == 1_000
    assert coletas == [1]
    assert smart_chamadas == [1]

    medidas[0] = {"total": 2_000, "used": 800, "free": 1_200}
    segunda = agent.op_storage_overview()
    assert coletas == [1]
    assert smart_chamadas == [1]
    assert segunda["disks"][0]["parts"][0]["usages"][0]["total"] == 2_000


def test_refresh_storage_bypasses_cache(agent_module, monkeypatch):
    agent = agent_module
    calls = []

    def collect():
        calls.append(len(calls) + 1)
        return {"marker": calls[-1], "disks": []}

    monkeypatch.setattr(agent, "_collect_storage_overview", collect)
    agent.op_storage_overview()
    refreshed = agent.op_refresh_storage()
    assert refreshed["marker"] == 2
    assert calls == [1, 2]
