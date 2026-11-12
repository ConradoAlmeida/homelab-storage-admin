from core.disk_table import enrich_disk_rows


def _usage(mount, total, used):
    return {
        "mount": mount,
        "total": total,
        "used": used,
        "free": total - used,
        "percent": round(used / total * 100, 1) if total else 0.0,
    }


def _part(name, fstype="ext4", size="1G", mounts=None, usages=None):
    return {
        "name": name,
        "fstype": fstype,
        "size": size,
        "mounts": mounts or [],
        "usages": usages or [],
    }


def _disk(name, parts, mounts=None):
    return {"name": name, "parts": parts, "mounts": mounts or []}


def test_agrega_uso_das_particoes():
    disco = _disk(
        "sda",
        [
            _part("sda1", usages=[_usage("/boot/efi", 100, 20)]),
            _part("sda2", usages=[_usage("/mnt/backup", 300, 60)]),
        ],
    )
    enrich_disk_rows([disco])
    display = disco["mount_display"]
    assert display["usage"] == {
        "total": 400,
        "used": 80,
        "free": 320,
        "percent": 20.0,
    }
    assert display["summary"] == "2 partições · 2 montagens"
    assert display["mount_count"] == 2


def test_sem_particoes_nao_quebra():
    disco = _disk("sda", [])
    enrich_disk_rows([disco])
    assert disco["mount_display"] is None


def test_particao_sem_montagem_aparece():
    disco = _disk("sda", [_part("sda1")])
    enrich_disk_rows([disco])
    display = disco["mount_display"]
    assert display["summary"] == "1 partição · sem montagem"
    assert display["expand_rows"][0]["usage"] is None
    assert display["expand_rows"][0]["mountpoint"] == ""


def test_contagens_com_plural():
    disco = _disk(
        "sda",
        [
            _part(f"sda{i}", usages=[_usage(f"/mnt/p{i}", 100, 10)])
            for i in range(1, 5)
        ],
    )
    enrich_disk_rows([disco])
    assert disco["mount_display"]["summary"] == "4 partições · 4 montagens"


def test_raid_membro_usa_uso_do_array():
    disco = _disk(
        "sdb",
        [_part("sdb1", "linux_raid_member", "2T")],
        mounts=["/mnt/data"],
    )
    volumes = [_usage("/mnt/data", 1000, 250)]
    enrich_disk_rows(
        [disco],
        raid={"mdstat": "md0 : active raid1 sdb1[0] sdc1[1]\n"},
        volumes=volumes,
        storage_root="/mnt/data",
    )
    display = disco["mount_display"]
    assert display["raid_chip"] is True
    assert display["raid_label"] == "RAID md0 → /mnt/data"
    assert display["usage"]["percent"] == 25.0
    assert display["expand_rows"][0]["chain"] == "sdb1 → md0 → /mnt/data"


def test_dois_membros_raid_recebem_o_mesmo_array():
    discos = [
        _disk("sdb", [_part("sdb1", "linux_raid_member")]),
        _disk("sdc", [_part("sdc1", "linux_raid_member")]),
    ]
    volumes = [_usage("/mnt/data", 1000, 250)]
    enrich_disk_rows(
        discos,
        raid={"mdstat": "md0 : active raid1 sdb1[0] sdc1[1]\n"},
        volumes=volumes,
        storage_root="/mnt/data",
    )
    for disco, membro in zip(discos, ("sdb1", "sdc1")):
        display = disco["mount_display"]
        assert display["raid_chip"] is True
        assert display["raid_label"] == "RAID md0 → /mnt/data"
        assert display["expand_rows"][0]["chain"].startswith(f"{membro} → md0")


def test_raid_sem_montagem_mostra_so_o_md():
    disco = _disk("sdb", [_part("sdb1", "linux_raid_member")])
    enrich_disk_rows(
        [disco],
        raid={"mdstat": "md0 : active raid1 sdb1[0]\n"},
    )
    display = disco["mount_display"]
    assert display["raid_chip"] is True
    assert display["raid_label"] == "RAID md0"
    assert display["usage"] is None
    assert display["expand_rows"][0]["chain"] == "sdb1 → md0"
