from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


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


def _preparar_usb(agent_module, monkeypatch, tmp_path, valor=b"conteudo"):
    dump = tmp_path / "gitea-20260101-000000.zip"
    dump.write_bytes(valor)
    montado = tmp_path / "usb"
    montado.mkdir()
    monkeypatch.setattr(agent_module, "_gitea_dump", lambda: dump)
    monkeypatch.setattr(
        agent_module,
        "_gitea_usb_disks",
        lambda: [{"name": "sdb", "path": "/dev/sdb", "has_filesystem": True}],
    )
    monkeypatch.setattr(
        agent_module, "_usb_montar", lambda disco: (montado, False)
    )
    monkeypatch.setattr(agent_module, "_usb_desmontar", lambda *a: None)
    return dump, montado


def test_backup_usb_ignora_chmod_de_exfat(agent_module, monkeypatch, tmp_path):
    dump, montado = _preparar_usb(agent_module, monkeypatch, tmp_path)
    original = os.chmod

    def chmod(caminho, modo):
        if str(caminho).endswith(".zip"):
            raise OSError("exFAT nao suporta chmod")
        return original(caminho, modo)

    monkeypatch.setattr(agent_module.os, "chmod", chmod)
    resultado = agent_module._gitea_backup("sdb")
    assert resultado["usb_verified"] is True
    assert (montado / "gitea" / dump.name).read_bytes() == b"conteudo"
    sidecar = montado / "gitea" / f"{dump.name}.sha256"
    assert resultado["sha256"] in sidecar.read_text()


def test_backup_usb_recusa_copia_corrompida(agent_module, monkeypatch, tmp_path):
    dump, montado = _preparar_usb(agent_module, monkeypatch, tmp_path)
    original = agent_module.shutil.copyfile

    def copyfile(origem, destino, *a, **k):
        if str(destino).endswith(".zip"):
            Path(destino).write_bytes(b"corrompido")
            return destino
        return original(origem, destino, *a, **k)

    monkeypatch.setattr(agent_module.shutil, "copyfile", copyfile)
    with pytest.raises(agent_module.AgentError):
        agent_module._gitea_backup("sdb")
    assert not (montado / "gitea" / dump.name).exists()
    assert not (montado / "gitea" / f"{dump.name}.sha256").exists()
    assert agent_module._gitea_status_read()["status"] == "failed"
