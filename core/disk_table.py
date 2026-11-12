"""Apresentação compacta da tabela de discos do dashboard.

Funções puras: recebem o dicionário de ``storage_overview`` do agente e
anexam ``mount_display`` a cada disco. Nada aqui chama o agente ou o banco.
"""
from __future__ import annotations

import re
from typing import Any

_MDSTAT_RE = re.compile(r"^(md\d+)\s*:\s*(\S+)\s+(.*)$")
_MEMBER_RE = re.compile(r"\b([a-z][a-z0-9]*\d+)\[\d+\]")


def _under(path: str | None, root: str | None) -> bool:
    if not path or not root:
        return False
    root = root.rstrip("/")
    if not root:
        return path.startswith("/")
    return path == root or path.startswith(root + "/")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _aggregate_usage(parts: list[dict]) -> dict | None:
    total = used = 0
    for part in parts:
        usages = part.get("usages") or []
        if not usages and part.get("usage"):
            usages = [part["usage"]]
        for usage in usages:
            total += _int(usage.get("total"))
            used += _int(usage.get("used"))
    if total <= 0:
        return None
    return {
        "total": total,
        "used": used,
        "free": total - used,
        "percent": round(used / total * 100, 1),
    }


def _volume_for_mount(mount: str, volumes: list[dict]) -> dict | None:
    if not mount:
        return None
    best: dict | None = None
    for volume in volumes:
        volume_mount = volume.get("mount")
        if volume_mount == mount:
            return volume
        if volume_mount and _under(mount, volume_mount):
            if best is None or len(volume_mount) > len(best.get("mount") or ""):
                best = volume
    return best


def _parse_mdstat(mdstat: str) -> dict[str, dict]:
    arrays: dict[str, dict] = {}
    for line in (mdstat or "").splitlines():
        match = _MDSTAT_RE.match(line)
        if not match:
            continue
        md, level, rest = match.groups()
        arrays[md] = {
            "level": level,
            "members": _MEMBER_RE.findall(rest),
        }
    return arrays


def _raid_mount(
    disk: dict,
    volumes: list[dict],
    usage_by_mount: dict[str, dict],
    storage_root: str,
) -> str:
    candidates: list[str] = []
    for mount in disk.get("mounts") or []:
        if mount and mount not in candidates:
            candidates.append(mount)
    for volume in volumes:
        mount = volume.get("mount")
        if mount and mount not in candidates:
            candidates.append(mount)
    for mount in usage_by_mount:
        if mount and mount not in candidates:
            candidates.append(mount)
    if storage_root:
        root = storage_root.rstrip("/") or "/"
        for mount in candidates:
            if mount == root or mount.startswith(root + "/"):
                return mount
    for mount in candidates:
        if mount and mount != "/":
            return mount
    if "/" in candidates:
        return "/"
    return candidates[0] if candidates else ""


def _derive_raid(
    disk: dict,
    parts: list[dict],
    raid_overview: dict | None,
    usage_by_mount: dict[str, dict],
    volumes: list[dict],
    storage_root: str,
) -> dict[str, dict]:
    arrays = _parse_mdstat((raid_overview or {}).get("mdstat") or "")
    if not arrays:
        return {}
    members = {
        part.get("name")
        for part in parts
        if part.get("fstype") == "linux_raid_member" and part.get("name")
    }
    if not members:
        return {}
    mount = _raid_mount(disk, volumes, usage_by_mount, storage_root)
    usage = _volume_for_mount(mount, volumes) or usage_by_mount.get(mount)
    result: dict[str, dict] = {}
    for md, info in arrays.items():
        for member in info["members"]:
            if member not in members:
                continue
            chain = f"{member} → {md}"
            label = f"RAID {md}"
            if mount:
                chain += f" → {mount}"
                label += f" → {mount}"
            result[member] = {
                "md": md,
                "mount": mount,
                "chain": chain,
                "label": label,
                "usage": usage,
            }
    return result


def derive_raid_display(
    disk: dict,
    parts: list[dict],
    raid_overview: dict | None = None,
    *,
    volumes: list[dict] | None = None,
    usage_by_mount: dict[str, dict] | None = None,
    storage_root: str = "",
) -> dict[str, dict]:
    """Public entry for the RAID derivation used by the dashboard and tests."""
    volumes = list(volumes or [])
    if usage_by_mount is None:
        usage_by_mount = {}
        for volume in volumes:
            mount = volume.get("mount")
            if mount:
                usage_by_mount[mount] = volume
    return _derive_raid(
        disk,
        parts,
        raid_overview,
        usage_by_mount,
        volumes,
        storage_root,
    )


def _expand_rows(parts: list[dict], raid_info: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for part in parts:
        usages = part.get("usages") or []
        if not usages and part.get("usage"):
            usages = [part["usage"]]
        info = raid_info.get(part.get("name"))
        base = {
            "name": part.get("name") or "",
            "fstype": part.get("fstype") or "",
            "size": part.get("size") or "",
        }
        if usages:
            for usage in usages:
                rows.append(
                    {
                        **base,
                        "mountpoint": usage.get("mount") or "",
                        "chain": info.get("chain", "") if info else "",
                        "usage": usage,
                    }
                )
            continue
        rows.append(
            {
                **base,
                "mountpoint": (
                    info.get("mount", "")
                    if info
                    else ", ".join(part.get("mounts") or [])
                ),
                "chain": info.get("chain", "") if info else "",
                "usage": info.get("usage") if info else None,
            }
        )
    return rows


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _summary(part_count: int, mount_count: int) -> str:
    if part_count == 0:
        return "sem partições"
    parts = _plural(part_count, "partição", "partições")
    mounts = (
        _plural(mount_count, "montagem", "montagens")
        if mount_count
        else "sem montagem"
    )
    return f"{parts} · {mounts}"


def enrich_disk_rows(
    disks: list[dict],
    *,
    raid: dict | None = None,
    volumes: list[dict] | None = None,
    storage_root: str = "",
) -> list[dict]:
    """Annex ``mount_display`` to each disk for the compact dashboard table."""
    volumes = list(volumes or [])
    usage_by_mount: dict[str, dict] = {}
    for disk in disks or []:
        for part in disk.get("parts") or []:
            usages = part.get("usages") or []
            if not usages and part.get("usage"):
                usages = [part["usage"]]
            for usage in usages:
                mount = usage.get("mount")
                if mount:
                    usage_by_mount.setdefault(mount, usage)
    for volume in volumes:
        mount = volume.get("mount")
        if mount:
            usage_by_mount[mount] = volume

    for disk in disks or []:
        parts = disk.get("parts") or []
        if not parts:
            disk["mount_display"] = None
            continue
        raid_info = derive_raid_display(
            disk,
            parts,
            raid,
            volumes=volumes,
            usage_by_mount=usage_by_mount,
            storage_root=storage_root,
        )
        rows = _expand_rows(parts, raid_info)
        aggregate = _aggregate_usage(parts)
        raid_usage = next(
            (info.get("usage") for info in raid_info.values() if info.get("usage")),
            None,
        )
        usage = aggregate or raid_usage
        mount_count = len(
            {row["mountpoint"] for row in rows if row.get("mountpoint")}
        )
        label = next(
            (info.get("label") for info in raid_info.values() if info.get("label")),
            "",
        )
        disk["mount_display"] = {
            "part_count": len(parts),
            "mount_count": mount_count,
            "summary": _summary(len(parts), mount_count),
            "raid_chip": bool(raid_info),
            "raid_label": label,
            "usage": usage,
            "expand_rows": rows,
        }
    return disks
