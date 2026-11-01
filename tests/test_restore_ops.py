from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_lock_orfao_so_deste_host_sem_restic(agent_module, monkeypatch):
    agent = agent_module
    monkeypatch.setattr(agent, "_nomes_deste_host", lambda: {"homelab"})
    monkeypatch.setattr(agent, "_pid_restic", lambda pid: False)
    texto = (
        "unable to create lock in backend: repository is already locked by "
        "PID 71289 on homelab by root (UID 0, GID 0)\n"
        "lock was created at 2026-10-26 22:33:28"
    )
    assert agent._lock_orfao(texto)
    monkeypatch.setattr(agent, "_nomes_deste_host", lambda: {"outro"})
    assert not agent._lock_orfao(texto)
    monkeypatch.setattr(agent, "_nomes_deste_host", lambda: {"homelab"})
    monkeypatch.setattr(agent, "_pid_restic", lambda pid: True)
    assert not agent._lock_orfao(texto)


def test_check_remove_lock_orfao_e_repete(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    disco = tmp_path / "disk"
    disco.mkdir()
    chave = tmp_path / "key"
    chave.write_text("segredo")
    disk = {
        "uuid": "abc",
        "label": "hdd700",
        "mountpoint": str(disco),
        "repo": str(disco / "restic"),
        "key_file": str(chave),
    }
    monkeypatch.setattr(agent.shutil, "which", lambda nome: "/usr/bin/restic")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: True)
    chamadas = []

    def fake_run(args, **kwargs):
        chamadas.append(list(args))
        if args[-1] == "unlock":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[-1] == "check" and any(item[-1] == "unlock" for item in chamadas[:-1]):
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=(
                "already locked by PID 9 on testhost by root\n"
                "lock was created at 2026-10-26"
            ),
        )

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    monkeypatch.setattr(agent, "_nomes_deste_host", lambda: {"testhost"})
    monkeypatch.setattr(agent, "_pid_restic", lambda pid: False)
    monkeypatch.setattr(agent, "_backup_health_write", lambda uuid, dados: dados)
    monkeypatch.setattr(agent, "log", lambda *a, **k: None)
    dados = agent._backup_check_disk(disk, read_data=False)
    assert dados["ok"] is True
    assert any(item[-1] == "unlock" for item in chamadas)


def test_snapshot_restore_rsync_volta_arquivo(agent_module):
    agent = agent_module
    share = Path(agent.STORAGE_ROOT) / "docs"
    share.mkdir(parents=True, exist_ok=True)
    snapdir = share / ".snapshots"
    agent.save_policies(
        {
            "docs": {
                "path": str(share),
                "enabled": True,
                "keep": 5,
                "backend": "rsync",
                "snapdir": str(snapdir),
            }
        }
    )
    (share / "arquivo.txt").write_text("antigo")
    nome = agent.op_snapshot_create("docs")["name"]
    (share / "arquivo.txt").write_text("novo")
    with pytest.raises(agent.AgentError):
        agent.op_snapshot_restore("docs", nome, confirmation="errado")
    agent.op_snapshot_restore("docs", nome, confirmation=nome)
    assert (share / "arquivo.txt").read_text() == "antigo"


def test_backup_restore_recusa_raiz_e_disco_de_backup(agent_module, monkeypatch):
    agent = agent_module
    with pytest.raises(agent.AgentError, match="raiz"):
        agent._destino_restic_ok("/")
    monkeypatch.setattr(
        agent, "ALLOWED_PATH_PREFIXES", (str(Path(agent.BACKUP_ROOT)) + "/",)
    )
    with pytest.raises(agent.AgentError, match="backup"):
        agent._destino_restic_ok(str(Path(agent.BACKUP_ROOT) / "hdd700"))


def test_gitea_restore_aplica_dump(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    dumps = tmp_path / "dumps"
    volume = tmp_path / "volume" / "data"
    volume.mkdir(parents=True)
    (volume / "gitea").mkdir()
    dumps.mkdir()
    zip_path = dumps / "gitea-20261028-113707.zip"
    with zipfile.ZipFile(zip_path, "w") as pacote:
        pacote.writestr("app.ini", "APP = 1\n")
        pacote.writestr("gitea.db", "sqlite")
    agent.GITEA_BACKUP_DIR = str(dumps)
    agent.GITEA_CONTAINER = "gitea"
    monkeypatch.setattr(agent, "_container_exists", lambda nome: True)
    monkeypatch.setattr(agent, "_gitea_volume", lambda: volume)
    monkeypatch.setattr(
        agent,
        "run_optional",
        lambda args, timeout=20: (0, "true", ""),
    )
    monkeypatch.setattr(agent, "run", lambda *a, **k: "")
    monkeypatch.setattr(agent, "log", lambda *a, **k: None)
    with pytest.raises(agent.AgentError, match="confirme"):
        agent.op_gitea_restore(zip_path.name, confirmation="outro.zip")
    resultado = agent.op_gitea_restore(zip_path.name, confirmation=zip_path.name)
    assert "app.ini" in resultado["applied"]
    assert (volume / "gitea" / "conf" / "app.ini").read_text() == "APP = 1\n"
    assert (volume / "gitea" / "gitea.db").read_text() == "sqlite"
