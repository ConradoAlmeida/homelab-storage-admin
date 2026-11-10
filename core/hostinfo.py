"""Funções puras para associar mounts a volumes e papéis de disco."""
from __future__ import annotations


def _under(path: str | None, root: str | None) -> bool:
    if not path or not root:
        return False
    root = root.rstrip("/")
    if not root:
        return path.startswith("/")
    return path == root or path.startswith(root + "/")


def disks_for_path(path: str | None, disks: list[dict]) -> list[dict]:
    """Discos cujo mount mais específico contém o caminho.

    Dois discos no mesmo mount (os membros de um RAID) entram juntos.
    """
    best = -1
    chosen: list[dict] = []
    for disk in disks:
        if not isinstance(disk, dict):
            continue
        for mount in disk.get("mounts") or []:
            if not mount or not _under(path, mount):
                continue
            length = len(mount)
            if length > best:
                best = length
                chosen = [disk]
            elif length == best and disk not in chosen:
                chosen.append(disk)
    chosen.sort(key=lambda disk: disk.get("name") or "")
    return chosen


def rotulo_discos(disks: list[dict]) -> str:
    """Nome e modelo, no formato visto na lista de shares."""
    if not disks:
        return ""
    nomes: list[str] = []
    modelos: list[str] = []
    for disk in disks:
        nome = (disk.get("name") or "").strip()
        if nome and nome not in nomes:
            nomes.append(nome)
        modelo = (disk.get("model") or "").strip()
        if modelo and modelo not in modelos:
            modelos.append(modelo)
    if not nomes:
        return ""
    titulo = "Disco" if len(nomes) == 1 else "Discos"
    base = " + ".join(nomes)
    if modelos:
        return f"{titulo} {base} · {', '.join(modelos)}"
    return f"{titulo} {base}"


def anexar_discos(itens: list[dict], disks: list[dict], chave: str = "path") -> list[dict]:
    for item in itens:
        if not isinstance(item, dict):
            continue
        do_caminho = disks_for_path(item.get(chave), disks)
        item["disk_label"] = rotulo_discos(do_caminho)
    return itens


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
    media_root: str | None = None,
) -> str:
    mounts = [mount for mount in (disk.get("mounts") or []) if mount]
    if any(mount == "/" for mount in mounts):
        return "sistema"
    if any(_under(mount, backup_root) for mount in mounts):
        return "backup"
    if media_root and any(_under(mount, media_root) for mount in mounts):
        return "mídia"
    if any(_under(mount, storage_root) for mount in mounts):
        return "dados/RAID"
    return "—"
