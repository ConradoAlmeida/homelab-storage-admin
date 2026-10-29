"""Agente falso só para pré-visualizar o layout no Windows."""

from __future__ import annotations

from .agent import AgentClient, AgentError

CAPS = {
    "btrfs": True,
    "restic": True,
    "smartctl": True,
    "hdparm": True,
    "mdadm": True,
    "hwmon_fans": True,
    "storage_root_mounted": True,
    "storage_root_fstype": "ext4",
    "snapshot_backend": "btrfs",
    "credenciais_backup": True,
    "gitea": True,
    "containers": True,
}

DISKS = [
    {
        "name": "sda",
        "path": "/dev/sda",
        "model": "Samsung 870",
        "serial": "S5XXXX",
        "size": "4T",
        "state": "active/idle",
        "mounts": ["/mnt/nas"],
        "fstype": "ext4",
        "label": "nas",
        "uuid": "disk-nas",
        "smart": {"temperature": 34, "health": "PASSED", "state": "ok"},
        "candidate": False,
        "reason": "disco de dados",
        "configured": False,
        "has_filesystem": True,
    },
    {
        "name": "sdb",
        "path": "/dev/sdb",
        "model": "WD Elements",
        "serial": "WXXXX",
        "size": "5T",
        "state": "standby",
        "mounts": ["/mnt/backup"],
        "mountpoint": "/mnt/backup",
        "fstype": "ext4",
        "label": "backup",
        "uuid": "disk-backup",
        "smart": {"temperature": None, "health": "PASSED", "state": "ok", "skipped": True},
        "candidate": True,
        "configured": True,
        "has_filesystem": True,
        "jobs": ["nas-noite"],
        "health": {"ok": True, "finished_at": "2026-10-28T04:12:00"},
        "extra_confirmation": False,
    },
    {
        "name": "sdc",
        "path": "/dev/sdc",
        "model": "Seagate USB",
        "serial": "STXXXX",
        "size": "2T",
        "state": "active",
        "mounts": [],
        "fstype": "",
        "label": "",
        "uuid": "disk-usb",
        "smart": {"temperature": 29, "health": "PASSED", "state": "ok"},
        "candidate": True,
        "configured": False,
        "has_filesystem": False,
        "reason": "",
        "extra_confirmation": False,
    },
]


class DemoAgent(AgentClient):
    def call(self, op: str, timeout: int | None = None, **payload):
        dados = _dados(op, payload)
        if dados is None:
            raise AgentError(f"Operação de demonstração não implementada: {op}")
        return dados


def _dados(op: str, payload: dict):
    if op == "host_capabilities":
        return CAPS
    if op == "df":
        return {
            "volumes": [
                {
                    "mount": "/",
                    "total": 64 * 1024**3,
                    "used": 12 * 1024**3,
                    "free": 52 * 1024**3,
                    "percent": 19,
                },
                {
                    "mount": "/mnt/nas",
                    "total": 4 * 1024**4,
                    "used": 3 * 1024**4,
                    "free": 1 * 1024**4,
                    "percent": 76,
                },
            ]
        }
    if op == "list_users":
        return [
            {
                "username": "conrado",
                "fullname": "Conrado",
                "groups": ["midia", "engenharia"],
                "enabled": True,
            },
            {
                "username": "ana",
                "fullname": "Ana",
                "groups": ["midia"],
                "enabled": True,
            },
            {
                "username": "visita",
                "fullname": "",
                "groups": [],
                "enabled": False,
            },
        ]
    if op == "list_groups":
        return ["conrado", "ana", "visita", "midia", "engenharia", "backup"]
    if op == "list_shares":
        return [
            {
                "name": "midia",
                "path": "/mnt/nas/midia",
                "backend": "samba",
                "browseable": True,
                "read_only": False,
                "valid_users": "midia",
                "comment": "Filmes e séries",
                "size": 800 * 1024**3,
                "size_snapshots": 40 * 1024**3,
                "size_total": 840 * 1024**3,
            },
            {
                "name": "docs",
                "path": "/mnt/nas/docs",
                "backend": "samba",
                "browseable": True,
                "read_only": False,
                "valid_users": "engenharia",
                "size": 12 * 1024**3,
                "size_snapshots": 1 * 1024**3,
                "size_total": 13 * 1024**3,
            },
        ]
    if op == "snapshot_usage":
        return [
            {
                "share": "midia",
                "path": "/mnt/nas/midia",
                "enabled": True,
                "keep": 7,
                "count": 5,
                "size": 40 * 1024**3,
            }
        ]
    if op == "storage_overview":
        return {
            "collected_at": "2026-10-28T06:00:00",
            "stale": False,
            "system": {
                "zones": [{"type": "cpu_thermal", "temp": 47.0}],
                "fans": [],
                "load": {"l1": 0.4, "l5": 0.3, "l15": 0.2},
                "cpu_percent": 8.0,
                "mem_total_mb": 8192,
                "mem_available_mb": 4200,
            },
            "disks": DISKS,
            "raid": {
                "mdstat": "md0 : active raid1 sda1[0] sdb1[1]\n      3907018539 blocks [2/2] [UU]",
                "detail": "/dev/md0:\n        Version : 1.2\n  Raid Level : raid1",
            },
            "btrfs": {
                "usage": "Data, RAID1: Size:2.00TiB, Used:1.40TiB",
                "stats": "[/dev/sda].write_io_errs    0",
                "scrub": "scrub status: finished",
            },
        }
    if op == "live_metrics":
        return {
            "system": {
                "zones": [{"type": "cpu_thermal", "temp": 47.0}],
                "fans": [],
                "load": {"l1": 0.4, "l5": 0.3, "l15": 0.2},
                "cpu_percent": 8.0,
                "mem_total_mb": 8192,
                "mem_available_mb": 4200,
            },
            "collected_at": "2026-10-28T22:20:00",
        }
    if op == "backup_overview":
        return {
            "restic": True,
            "disks": DISKS,
            "jobs": [
                {
                    "name": "nas-noite",
                    "enabled": True,
                    "disk_uuid": "disk-backup",
                    "disk_label": "WD Elements",
                    "sources": ["midia", "docs"],
                    "schedule": {"label": "diário 03:30"},
                    "retention": {"daily": 7, "weekly": 4, "monthly": 6},
                    "status": {
                        "status": "success",
                    },
                    "last_run_label": "hoje 03:31",
                    "next_run_label": "amanhã 03:30",
                }
            ],
        }
    if op == "arquivos_jobs":
        return {
            "dir": "/var/backups/moya-credenciais",
            "jobs": [
                {
                    "name": "credenciais",
                    "label": "Credenciais",
                    "enabled": True,
                    "agenda": "diário 03:30",
                    "retention_days": 30,
                    "next_run": "2026-10-29T03:30",
                    "sources": [{"name": "banco"}],
                    "status": {
                        "status": "success",
                        "ok": True,
                        "finished_at": "2026-10-28T03:31:00",
                    },
                    "archives_count": 7,
                }
            ],
        }
    if op == "health_overview":
        return {
            "ok": False,
            "alerts": [
                {
                    "level": "warn",
                    "title": "Volume /mnt/nas em 76%",
                    "detail": "Livre 1,0 TB de 4,0 TB.",
                },
                {
                    "level": "info",
                    "title": "Disco sdb em standby",
                    "detail": "SMART não lido para não acordar o disco.",
                },
            ],
            "volumes": [],
        }
    if op == "network_overview":
        return {
            "interfaces": [
                {
                    "name": "eth0",
                    "state": "up",
                    "cidr": "192.168.0.10/24",
                    "speed_mbps": 1000,
                    "mac": "dc:a6:32:00:00:01",
                    "signal_dbm": None,
                },
                {
                    "name": "wlan0",
                    "state": "up",
                    "cidr": "192.168.0.11/24",
                    "speed_mbps": 300,
                    "mac": "dc:a6:32:00:00:02",
                    "signal_dbm": -54,
                },
            ],
            "routes": [
                "default via 192.168.0.1 dev eth0 proto dhcp src 192.168.0.10 metric 100",
                "192.168.0.0/24 dev eth0 proto kernel scope link src 192.168.0.10 metric 100",
            ],
            "listening": [
                {"local": "127.0.0.1:8060", "process": "gunicorn", "state": "LISTEN"},
                {"local": "0.0.0.0:445", "process": "smbd", "state": "LISTEN"},
            ],
            "containers": [
                {"name": "moya-caddy", "ports": "80/tcp, 443/tcp", "status": "Up 2 days"},
                {"name": "pihole", "ports": "53/tcp, 53/udp", "status": "Up 2 days"},
            ],
            "firewall": "ativo",
            "rules": [
                "To                         Action      From",
                "--                         ------      ----",
                "22/tcp                     ALLOW IN    Anywhere",
                "80/tcp                     ALLOW IN    Anywhere",
                "445/tcp                    ALLOW IN    192.168.0.0/24",
            ],
        }
    if op == "network_metrics":
        return {
            "active": {
                "name": "eth0",
                "state": "up",
                "ssid": "",
                "rx_mbps": 12.4,
                "tx_mbps": 3.1,
                "rx_mb_s": 1.55,
                "tx_mb_s": 0.39,
                "speed_mbps": 1000,
                "link_rx_mbps": None,
                "signal_dbm": None,
            }
        }
    if op == "containers_overview":
        return {
            "runtime": "docker",
            "error": "",
            "containers": [
                {
                    "name": "moya-caddy",
                    "id": "3f2a1b0c9d8e",
                    "image": "caddy:2-alpine",
                    "state": "running",
                    "status": "Up 3 days",
                    "running": True,
                    "health": "healthy",
                    "restart_count": 0,
                    "project": "infra",
                    "service": "caddy",
                    "ports": ["0.0.0.0:80->80/tcp", "0.0.0.0:443->443/tcp"],
                },
                {
                    "name": "pihole",
                    "id": "9a8b7c6d5e4f",
                    "image": "pihole/pihole:latest",
                    "state": "running",
                    "status": "Up 3 days",
                    "running": True,
                    "health": "",
                    "restart_count": 0,
                    "project": "infra",
                    "service": "pihole",
                    "ports": ["0.0.0.0:53->53/tcp", "0.0.0.0:53->53/udp"],
                },
                {
                    "name": "moya-credenciais",
                    "id": "1a2b3c4d5e6f",
                    "image": "moya_credenciais_app-credenciais",
                    "state": "running",
                    "status": "Up 3 days",
                    "running": True,
                    "health": "healthy",
                    "restart_count": 1,
                    "project": "moya-credenciais",
                    "service": "credenciais",
                    "ports": ["127.0.0.1:8080->8080/tcp"],
                },
                {
                    "name": "teste-antigo",
                    "id": "0f0e0d0c0b0a",
                    "image": "alpine:3.20",
                    "state": "exited",
                    "status": "Exited (0) 2 days ago",
                    "running": False,
                    "health": "",
                    "restart_count": 0,
                    "project": "",
                    "service": "",
                    "ports": [],
                },
            ],
        }
    if op == "container_action":
        return {
            "name": payload.get("name", ""),
            "action": payload.get("action", ""),
            "message": "",
        }
    if op == "container_logs":
        nome = payload.get("name", "container")
        return {
            "name": nome,
            "tail": payload.get("tail", 200),
            "runtime": "docker",
            "logs": (
                f"2026-10-28T23:40:01Z {nome} | iniciando\n"
                f"2026-10-28T23:40:02Z {nome} | pronto\n"
                f"2026-10-28T23:41:10Z {nome} | GET / 200\n"
            ),
        }
    if op == "backup_snapshots":
        return {"snapshots": [], "errors": []}
    if op == "cold_overview":
        return {
            "disks": DISKS,
            "restic": True,
            "primary": {},
            "primary_error": "",
            "config": None,
            "status": {},
        }
    if op == "gitea_overview":
        return {"status": {}}
    return None
