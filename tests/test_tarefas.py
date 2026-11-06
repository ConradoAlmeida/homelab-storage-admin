from __future__ import annotations

import pytest


def test_confirmacao_errada_nao_grava_tarefa(agent_module, tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "TASK_DIR", str(tmp_path / "tasks"))
    with pytest.raises(agent_module.AgentError, match="confirme"):
        agent_module._despachar(
            "snapshot_restore",
            {
                "share": "docs",
                "name": "@GMT-2026.01.01-00.00.00",
                "confirmation": "errado",
            },
        )
    assert not (tmp_path / "tasks").exists()


def test_disparo_devolve_e_o_worker_conclui(agent_module, tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "TASK_DIR", str(tmp_path / "tasks"))
    executou = []

    def falso(**kwargs):
        agent_module._checkpoint()
        executou.append(kwargs)
        return {"ok": True, "feito": True}

    monkeypatch.setitem(agent_module.OPS, "backup_check", falso)

    def run_ok(args, **_kwargs):
        assert args[:3] == ["systemctl", "start", "--no-block"]
        assert args[3].startswith("homelab-task@")
        return ""

    monkeypatch.setattr(agent_module, "run", run_ok)
    dados = agent_module._despachar("backup_check", {"uuid": "abc"})
    assert dados == {
        "started": True,
        "task": dados["task"],
        "status": "running",
    }
    assert executou == []
    assert agent_module.op_task_status(dados["task"])["status"] == "running"
    agent_module._tarefa_executar(dados["task"])
    assert executou == [{"uuid": "abc"}]
    status = agent_module.op_task_status(dados["task"])
    assert status["status"] == "ok"
    assert status["result"]["feito"] is True
    assert "payload" not in status


def test_sem_unit_a_thread_executa(agent_module, tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "TASK_DIR", str(tmp_path / "tasks"))

    def falso(**_kwargs):
        agent_module._checkpoint()
        return {"name": "@GMT-2026.11.04-12.00.00"}

    monkeypatch.setitem(agent_module.OPS, "snapshot_create", falso)

    def run_falha(*_args, **_kwargs):
        raise agent_module.AgentError("unit ausente")

    monkeypatch.setattr(agent_module, "run", run_falha)

    class Imediata:
        def __init__(self, target, args, daemon, name):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(agent_module.threading, "Thread", Imediata)
    dados = agent_module._despachar("snapshot_create", {"share": "docs"})
    assert dados["status"] == "running"
    status = agent_module.op_task_status(dados["task"])
    assert status["status"] == "ok"
    assert "Snapshot criado" in status["message"]


def test_cold_copy_acompanha_o_status_do_servico(agent_module, tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "TASK_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(
        agent_module,
        "op_cold_copy",
        lambda **_: {"started": True, "device": "/dev/sdb"},
    )
    dados = agent_module._despachar("cold_copy", {})
    assert agent_module.op_task_status(dados["task"])["status"] == "running"
    agent_module._write_cold_status(
        {
            "status": "success",
            "started_at": "2099-01-01T00:00:00",
            "finished_at": "2099-01-01T00:00:01",
            "message": "restic copy + check OK",
            "snapshots": 3,
        }
    )
    status = agent_module.op_task_status(dados["task"])
    assert status["status"] == "ok"
    assert status["result"]["snapshots"] == 3


def test_disco_do_sistema_nao_entra_na_fila(agent_module, tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "TASK_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(agent_module.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    disco = {
        "path": "/dev/sda",
        "name": "sda",
        "candidate": False,
        "system": True,
        "mounts": ["/"],
        "reason": "disco do sistema",
        "extra_confirmation": False,
        "required_phrase": "FORMATAR /dev/sda",
    }
    monkeypatch.setattr(agent_module, "_backup_disks", lambda config: [disco])
    monkeypatch.setattr(
        agent_module, "_load_backup_config", lambda: {"disks": [], "jobs": []}
    )
    with pytest.raises(agent_module.AgentError, match="disco do sistema"):
        agent_module._despachar(
            "backup_disk_setup",
            {
                "device": "/dev/sda",
                "label": "backup",
                "confirmation": "FORMATAR /dev/sda",
                "allow_existing": False,
            },
        )
    assert not (tmp_path / "tasks").exists()


def test_apt_upgrade_nao_roda_no_precheck(agent_module, tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "TASK_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(agent_module, "SYSTEM_MANAGE", True)
    monkeypatch.setattr(
        agent_module.shutil, "which", lambda nome: "/usr/bin/apt-get" if nome == "apt-get" else None
    )

    def proibido(*_args, **_kwargs):
        raise AssertionError("apt nao deve rodar no precheck")

    monkeypatch.setattr(agent_module.subprocess, "run", proibido)

    def run_ok(args, **_kwargs):
        assert args[:3] == ["systemctl", "start", "--no-block"]
        return ""

    monkeypatch.setattr(agent_module, "run", run_ok)
    with pytest.raises(agent_module.AgentError, match="ATUALIZAR"):
        agent_module._despachar("apt_upgrade", {"confirmation": "errado"})
    dados = agent_module._despachar("apt_upgrade", {"confirmation": "ATUALIZAR"})
    assert dados["status"] == "running"
    assert dados["started"] is True


def test_journal_rede_usa_identificador(agent_module, monkeypatch):
    monkeypatch.setattr(
        agent_module.shutil,
        "which",
        lambda nome: "/usr/bin/journalctl" if nome == "journalctl" else None,
    )
    vistos = []

    def falso(argv, **_kwargs):
        vistos.append(list(argv))

        class Proc:
            stdout = ""
            stderr = ""
            returncode = 0

        return Proc()

    monkeypatch.setattr(agent_module.subprocess, "run", falso)
    dados = agent_module.op_journal(filtro="rede")
    assert dados["lines"] == []
    argv = vistos[0]
    assert "-t" in argv
    assert "systemd-networkd-wait-online" in argv
    assert "-u" not in argv


def test_ssh_keys_le_authorized_keys(agent_module, tmp_path, monkeypatch):
    home = tmp_path / "home" / "ana"
    sshdir = home / ".ssh"
    sshdir.mkdir(parents=True)
    (sshdir / "id_ed25519").write_text("privada\n")
    (sshdir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA ana\n")
    autorizado = sshdir / "authorized_keys"
    autorizado.write_text("ssh-ed25519 BBBB notebook\n")

    class Ent:
        pw_uid = 1000
        pw_name = "ana"
        pw_dir = str(home)

    monkeypatch.setattr(agent_module.pwd, "getpwall", lambda: [Ent()])

    def run(args, **_kwargs):
        assert args[:2] == ["ssh-keygen", "-lf"]
        assert args[2] == str(autorizado)
        return "256 SHA256:abc notebook (ED25519)\n"

    monkeypatch.setattr(agent_module, "run", run)
    assert agent_module.op_ssh_keys() == {
        "keys": [
            {
                "user": "ana",
                "path": str(autorizado),
                "fingerprint": "SHA256:abc",
                "type": "ED25519",
                "comment": "notebook",
            }
        ]
    }


def test_sudo_recusa_sem_colocar_senha_no_argv(agent_module, monkeypatch):
    vistos = []

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "Sorry, try again."

    def run(argv, **kwargs):
        vistos.append((list(argv), kwargs.get("input")))
        return Proc()

    monkeypatch.setattr(agent_module.subprocess, "run", run)
    monkeypatch.setattr(agent_module.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    monkeypatch.setattr(
        agent_module.pwd,
        "getpwnam",
        lambda nome: type("C", (), {"pw_name": nome, "pw_gid": 1000, "pw_uid": 1000, "pw_dir": "/home/ana"})(),
    )
    with pytest.raises(agent_module.AgentError, match="recusada"):
        agent_module._sudo_confere("ana", "segredo")
    assert vistos
    assert "segredo" not in vistos[0][0]
    assert vistos[0][1] == "segredo\n"


def test_terminal_nao_abre_com_sudo_recusado(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "TERMINAL_ENABLE", True)

    def recusa(usuario, senha):
        raise agent_module.AgentError("Senha sudo recusada")

    def aborta(*_args, **_kwargs):
        raise AssertionError("fork nao deve rodar")

    monkeypatch.setattr(agent_module, "_sudo_confere", recusa)
    monkeypatch.setattr(agent_module.os, "fork", aborta)
    with pytest.raises(agent_module.AgentError, match="recusada"):
        agent_module.op_terminal_open(user="ana", password="errada")
