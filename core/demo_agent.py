"""Agente falso só para pré-visualizar o layout no Windows."""

from __future__ import annotations

import base64
import re

from .agent import AgentClient, AgentError

_VERSOES_AGENDA = {
    "per_day": 2,
    "first_time": "00:05",
    "times": ["00:05", "12:05"],
    "label": "2x/dia as 00:05 e 12:05",
}


def _demo_snapshot_times(per_day, first_time):
    total = int(per_day)
    if total < 1 or total > 24:
        raise AgentError("Copias por dia deve ficar entre 1 e 24")
    match = re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", (first_time or "").strip())
    if not match:
        raise AgentError("Horario invalido; use HH:MM")
    inicio = int(match.group(1)) * 60 + int(match.group(2))
    passo = 1440 / total
    horarios = []
    for indice in range(total):
        minutos = int(round(inicio + indice * passo)) % 1440
        horarios.append(f"{minutos // 60:02d}:{minutos % 60:02d}")
    return horarios


def _demo_schedule_label(horarios):
    if len(horarios) == 1:
        return f"1×/dia às {horarios[0]}"
    if len(horarios) == 24:
        return "24×/dia, a cada hora"
    return f"{len(horarios)}×/dia às " + ", ".join(horarios[:-1]) + f" e {horarios[-1]}"

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
    "jellyfin": True,
    "containers": True,
    "firewall": True,
    "apt": True,
    "journal": True,
    "systemctl": True,
    "system_manage": True,
    "terminal_enable": True,
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

    def _linha_json(self, caminho, payload, *, timeout: int | None = None):
        op = str(payload.get("op") or "")
        if op == "terminal_open":
            return {"session_id": "demosess12345678", "cols": 80, "rows": 24}
        if op == "terminal_io":
            return {"output_b64": base64.b64encode(b"demo@homelab:~$ ").decode("ascii")}
        if op == "terminal_close":
            return {"closed": True}
        raise AgentError("Socket de terminal indisponível na demonstração.")


_GATILHOS = {
    "backup_disk_setup",
    "cold_prepare",
    "cold_copy",
    "backup_restore",
    "backup_check",
    "gitea_restore",
    "arquivos_job_restore",
    "arquivos_job_verify",
    "arquivos_job_usb_backup",
    "credenciais_backup_run",
    "credenciais_backup_verify",
    "credenciais_backup_restore",
    "snapshot_create",
    "snapshot_restore",
    "snapshot_policy_save",
    "apt_check",
    "apt_upgrade",
}
_DEMO_TAREFAS: dict[str, dict] = {}
_DEMO_SEQ = 0


def _demo_disparar(op: str) -> dict:
    global _DEMO_SEQ
    _DEMO_SEQ += 1
    task = f"demo{_DEMO_SEQ:02d}-abcd1234"
    _DEMO_TAREFAS[task] = {"op": op, "ticks": 0}
    return {"started": True, "task": task, "status": "running"}


def _demo_status(task: str) -> dict:
    item = _DEMO_TAREFAS.get(task)
    if item is None:
        return {
            "status": "failed",
            "message": "Tarefa nao encontrada.",
            "op": "",
            "result": {},
        }
    item["ticks"] += 1
    if item["ticks"] < 2:
        return {
            "status": "running",
            "message": "Em andamento…",
            "op": item["op"],
            "result": {},
        }
    result: dict = {
        "recovery_password": "demo-senha-restic",
        "device": "/dev/sdc",
        "mountpoint": "/mnt/backup/demo",
        "repo": "/mnt/backup/demo/restic",
        "share": "docs",
        "name": "@GMT-2026.11.04-12.00.00",
    }
    if item["op"] == "apt_check":
        result = {"upgradable": ["curl", "git"], "count": 2, "preview": ""}
    elif item["op"] == "apt_upgrade":
        result = {"ok": True, "log_tail": ""}
    return {
        "status": "ok",
        "message": "Concluído.",
        "op": item["op"],
        "result": result,
    }


def _dados(op: str, payload: dict):
    if op in _GATILHOS:
        return _demo_disparar(op)
    if op == "task_status":
        return _demo_status(str(payload.get("task") or ""))
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
                "username": "barbara.luz",
                "fullname": "",
                "groups": ["barbara.luz"],
                "enabled": True,
            },
            {
                "username": "barbetta",
                "fullname": "",
                "groups": ["barbetta", "veronte"],
                "enabled": True,
            },
            {
                "username": "conrado",
                "fullname": "Conrado Almeida",
                "groups": [
                    "adm",
                    "casa",
                    "casa_ro",
                    "casa_rw",
                    "cdrom",
                    "conrado",
                    "dip",
                    "docker",
                    "documentos",
                    "drawings",
                    "impressao3d",
                    "jellyfin",
                    "kicad",
                    "lxd",
                    "midia",
                    "pessoal_caio",
                    "pessoal_conrado",
                    "pessoal_nicole",
                    "plugdev",
                    "projetos",
                    "sudo",
                    "veronte",
                ],
                "enabled": True,
            },
            {
                "username": "joao",
                "fullname": "",
                "groups": ["cnc", "joao"],
                "enabled": True,
            },
            {
                "username": "lucas",
                "fullname": "",
                "groups": ["lucas", "veronte"],
                "enabled": True,
            },
            {
                "username": "renato",
                "fullname": "",
                "groups": ["cnc", "renato"],
                "enabled": True,
            },
            {
                "username": "rubens",
                "fullname": "",
                "groups": ["drawings", "impressao3d", "kicad", "rubens", "veronte"],
                "enabled": True,
            },
            {
                "username": "rubens.godoi",
                "fullname": "",
                "groups": [
                    "drawings",
                    "impressao3d",
                    "kicad",
                    "rubens.godoi",
                    "veronte",
                ],
                "enabled": True,
            },
        ]
    if op == "list_groups":
        return [
            "barbara.luz",
            "barbetta",
            "casa",
            "casa_ro",
            "casa_rw",
            "cnc",
            "conrado",
            "documentos",
            "drawings",
            "impressao3d",
            "jellyfin",
            "joao",
            "kicad",
            "lucas",
            "midia",
            "pessoal_caio",
            "pessoal_conrado",
            "pessoal_nicole",
            "projetos",
            "renato",
            "rubens",
            "rubens.godoi",
            "veronte",
        ]
    if op in {"list_shares", "share_sizes"}:
        shares = [
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
        if op == "share_sizes":
            return {"pending": False, "error": "", "shares": shares}
        return shares
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
                    "ports": [
                        "0.0.0.0:80->80/tcp",
                        "0.0.0.0:443->443/tcp",
                        "0.0.0.0:2019->2019/tcp",
                        "127.0.0.1:8080->8080/tcp",
                    ],
                },
                {
                    "name": "homelab-storage-admin",
                    "id": "aa11bb22cc33",
                    "image": "homelab-storage-admin:local",
                    "state": "running",
                    "status": "Up 2 hours",
                    "running": True,
                    "health": "healthy",
                    "restart_count": 0,
                    "project": "homelab",
                    "service": "web",
                    "ports": ["127.0.0.1:8060->8060/tcp"],
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
    if op == "torrent_overview":
        return {
            "libraries": [
                {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"},
                {"id": "series", "name": "Séries", "path": "/mnt/jellyfin/series"},
            ],
            "libraries_error": "",
            "client": {"available": True, "version": "v5.0.1", "reason": ""},
            "torrents": [
                {
                    "hash": "a" * 40,
                    "name": "Exemplo",
                    "progress": 42,
                    "progress_label": "42%",
                    "state": "downloading",
                    "state_label": "baixando",
                    "speed": "1,2 MB/s",
                    "eta": "12 min",
                    "size": "2,0 GB",
                    "library": "Filmes",
                    "active": True,
                    "can_pause": True,
                    "can_resume": False,
                }
            ],
            "error": "",
            "active": True,
        }
    if op == "torrent_add":
        nomes = {"filmes": "Filmes", "series": "Séries"}
        escolhida = str(payload.get("library") or "filmes")
        return {
            "library": nomes.get(escolhida, escolhida),
            "path": "/mnt/jellyfin/" + escolhida,
        }
    if op == "torrent_action":
        return {"hash": payload.get("torrent_hash", ""), "action": payload.get("action", "")}
    if op == "library_merge_dir":
        return {
            "ok": True,
            "de": payload.get("source", ""),
            "para": payload.get("dest", ""),
            "motivo": "",
        }
    if op == "snapshot_policy_save":
        return {
            "share": payload.get("share", ""),
            "path": "/mnt/nas/" + str(payload.get("share", "")),
            "enabled": bool(payload.get("enabled", True)),
            "keep": int(payload.get("keep") or 7),
            "backend": "rsync",
            "snapdir": "",
            "created": "@GMT-demo" if payload.get("create_now") else None,
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
    if op == "versoes_schedule":
        return dict(_VERSOES_AGENDA)
    if op == "versoes_schedule_save":
        per_day = payload.get("per_day")
        first_time = str(payload.get("first_time") or "").strip()
        try:
            total = int(per_day)
        except (TypeError, ValueError) as exc:
            raise AgentError("Copias por dia deve ser um numero entre 1 e 24") from exc
        horarios = _demo_snapshot_times(total, first_time)
        _VERSOES_AGENDA.update(
            {
                "per_day": total,
                "first_time": first_time,
                "times": horarios,
                "label": _demo_schedule_label(horarios),
            }
        )
        return dict(_VERSOES_AGENDA)
    if op == "gitea_overview":
        return {"status": {}}
    if op == "host_info":
        return {
            "hostname": "demo-pi",
            "friendly_name": "Homelab Storage",
            "system": "Debian GNU/Linux 13 (trixie)",
            "kernel": "6.12.0-demo",
            "datetime": "2026-11-06 14:00:00 (America/Sao_Paulo)",
        }
    if op == "ssh_keys":
        return {
            "keys": [
                {
                    "user": "demo",
                    "path": "/home/demo/.ssh/id_ed25519",
                    "fingerprint": "SHA256:AbCdEf123",
                    "type": "ED25519",
                    "comment": "demo@homelab",
                }
            ]
        }
    if op == "journal":
        filtro = str(payload.get("filtro") or "sistema")
        if filtro == "container":
            return {
                "name": payload.get("name") or "caddy",
                "tail": int(payload.get("tail") or 50),
                "logs": "2026-11-06 demo | log de container\n",
                "runtime": "docker",
            }
        return {
            "lines": [
                f"2026-11-06T14:00:01Z demo {filtro}: mensagem de journal",
            ],
            "filtro": filtro,
            "count": 1,
        }
    if op == "systemd_list_units":
        return {
            "units": [
                {
                    "unit": "apparmor.service",
                    "load": "loaded",
                    "active": "active",
                    "sub": "exited",
                },
                {
                    "unit": "apport-autoreport.service",
                    "load": "loaded",
                    "active": "inactive",
                    "sub": "dead",
                },
                {
                    "unit": "apport.service",
                    "load": "loaded",
                    "active": "active",
                    "sub": "exited",
                },
                {
                    "unit": "smbd.service",
                    "load": "loaded",
                    "active": "failed",
                    "sub": "failed",
                },
            ]
        }
    if op == "systemd_unit_action":
        return {"unit": payload.get("unit"), "action": payload.get("action"), "ok": True}
    if op == "apt_check":
        return {"upgradable": ["curl"], "count": 1, "preview": ""}
    if op == "apt_upgrade":
        return {"ok": True, "log_tail": ""}
    return None
