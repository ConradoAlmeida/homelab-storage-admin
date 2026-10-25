"""Funções puras para associar mounts a volumes e papéis de disco."""
from __future__ import annotations


def _under(path: str | None, root: str | None) -> bool:
    if not path or not root:
        return False
    root = root.rstrip("/")
    if not root:
        return path.startswith("/")
    return path == root or path.startswith(root + "/")


def volume_for(path: str | None, volumes: list[dict]) -> dict | None:
    if not path:
        return None
    matches = [
        volume
        for volume in volumes
        if _under(path, volume.get("mount"))
    ]
    if not matches:
        return None
    return max(matches, key=lambda volume: len(volume.get("mount") or ""))


def disk_role(
    disk: dict,
    storage_root: str,
    backup_root: str,
) -> str:
    mounts = [mount for mount in (disk.get("mounts") or []) if mount]
    if any(mount == "/" for mount in mounts):
        return "sistema"
    if any(_under(mount, backup_root) for mount in mounts):
        return "backup"
    if any(_under(mount, storage_root) for mount in mounts):
        return "dados/RAID"
    return "—"
