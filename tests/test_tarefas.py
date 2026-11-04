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
