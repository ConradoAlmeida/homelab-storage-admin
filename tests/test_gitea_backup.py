from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def test_download_do_dump_reusa_o_arquivo_no_mesmo_disco(agent_module, tmp_path, monkeypatch):
    origem_dir = tmp_path / "gitea"
    origem_dir.mkdir()
    origem = origem_dir / "gitea-20261028-113707.zip"
    origem.write_bytes(b"zip")
    data = tmp_path / "data"
    (data / "downloads").mkdir(parents=True)
    monkeypatch.setattr(agent_module, "GITEA_BACKUP_DIR", str(origem_dir))
    monkeypatch.setattr(agent_module, "DATA_DIR", str(data))
    monkeypatch.setattr(agent_module, "DOWNLOAD_DIR", str(data / "downloads"))

    resultado = agent_module.op_gitea_download("gitea-20261028-113707.zip")

    alvo = data / resultado["relative"]
    assert alvo.is_file()
    assert alvo.stat().st_ino == origem.stat().st_ino
    assert origem.read_bytes() == b"zip"


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


def _preparar_systemd(agent_module, monkeypatch):
    """Grava o unit num diretório temporário e não chama o systemctl do host."""
    pasta = Path(agent_module.SYSTEMD_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    chamadas = []

    def run_optional(args, timeout=30):
        chamadas.append(list(args))
        return (0, "", "")

    monkeypatch.setattr(agent_module, "run_optional", run_optional)
    return pasta / agent_module.GITEA_TIMER, chamadas


def test_agenda_diaria_grava_timer(agent_module, monkeypatch):
    timer, chamadas = _preparar_systemd(agent_module, monkeypatch)
    dados = agent_module.op_gitea_schedule_save(
        enabled=True, frequency="daily", time="05:00"
    )
    assert dados["on_calendar"] == "*-*-* 05:00:00"
    texto = timer.read_text()
    assert "OnCalendar=*-*-* 05:00:00" in texto
    assert f"Unit={agent_module.GITEA_TIMER_UNIT}" in texto
    assert ["systemctl", "enable", "--now", agent_module.GITEA_TIMER] in chamadas
    assert not any(chamada[0] != "systemctl" for chamada in chamadas)


def test_agenda_semanal_segunda(agent_module, monkeypatch):
    timer, chamadas = _preparar_systemd(agent_module, monkeypatch)
    dados = agent_module.op_gitea_schedule_save(
        enabled=True, frequency="weekly", time="05:00", weekday=0
    )
    assert dados["on_calendar"] == "Mon *-*-* 05:00:00"
    assert "OnCalendar=Mon *-*-* 05:00:00" in timer.read_text()
    assert ["systemctl", "enable", "--now", agent_module.GITEA_TIMER] in chamadas


def test_agenda_mensal_dia_1(agent_module, monkeypatch):
    timer, chamadas = _preparar_systemd(agent_module, monkeypatch)
    dados = agent_module.op_gitea_schedule_save(
        enabled=True, frequency="monthly", time="05:00", monthday=1
    )
    assert dados["on_calendar"] == "*-*-01 05:00:00"
    assert "OnCalendar=*-*-01 05:00:00" in timer.read_text()
    assert ["systemctl", "enable", "--now", agent_module.GITEA_TIMER] in chamadas


def test_agenda_recusa_horario_e_dia_invalidos(agent_module, monkeypatch):
    _timer, chamadas = _preparar_systemd(agent_module, monkeypatch)
    with pytest.raises(agent_module.AgentError, match="Horario invalido"):
        agent_module.op_gitea_schedule_save(enabled=True, time="25:00")
    with pytest.raises(agent_module.AgentError, match="entre 1 e 28"):
        agent_module.op_gitea_schedule_save(
            enabled=True, frequency="monthly", time="05:00", monthday=31
        )
    assert chamadas == []


def test_agenda_desligada_remove_timer_e_mantem_json(agent_module, monkeypatch):
    timer, chamadas = _preparar_systemd(agent_module, monkeypatch)
    agent_module.op_gitea_schedule_save(
        enabled=True, frequency="daily", time="06:00"
    )
    assert timer.is_file()
    agent_module.op_gitea_schedule_save(
        enabled=False, frequency="weekly", time="06:00", weekday=2
    )
    assert not timer.is_file()
    gravado = json.loads(Path(agent_module.GITEA_SCHEDULE).read_text())
    assert gravado["enabled"] is False
    assert gravado["frequency"] == "weekly"
    assert gravado["weekday"] == 2
    assert gravado["next_run"] is None
    assert ["systemctl", "disable", "--now", agent_module.GITEA_TIMER] in chamadas


def test_agenda_sem_systemd_nao_falha(agent_module, monkeypatch, tmp_path):
    ausente = tmp_path / "sem-systemd"
    chamadas = []

    def run_optional(args, timeout=30):
        chamadas.append(list(args))
        return (0, "", "")

    monkeypatch.setattr(agent_module, "SYSTEMD_DIR", str(ausente))
    monkeypatch.setattr(agent_module, "run_optional", run_optional)
    dados = agent_module.op_gitea_schedule_save(
        enabled=True, frequency="daily", time="05:00"
    )
    assert dados["enabled"] is True
    assert Path(agent_module.GITEA_SCHEDULE).is_file()
    assert chamadas == []


def test_overview_inclui_agenda_desligada(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "run_optional", lambda *a, **k: (0, "", ""))
    visao = agent_module.op_gitea_overview()
    agenda = visao["schedule"]
    assert agenda["enabled"] is False
    assert agenda["time"] == "05:00"


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
