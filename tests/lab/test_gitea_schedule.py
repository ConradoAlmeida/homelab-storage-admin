"""Timer real do dump do Gitea. Só roda na VM, como root."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ..conftest import load_agent
from .conftest import lab_enabled

pytestmark = pytest.mark.lab

TIMER = "homelab-gitea-backup.timer"
UNIT = Path("/etc/systemd/system") / TIMER
STAMP = Path("/var/lib/systemd/timers") / f"stamp-{TIMER}"
SERVICO = "homelab-gitea-backup@host.service"


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _limpar(agenda: Path) -> None:
    _systemctl("stop", SERVICO)
    _systemctl("disable", "--now", TIMER)
    _systemctl("reset-failed", SERVICO)
    UNIT.unlink(missing_ok=True)
    STAMP.unlink(missing_ok=True)
    agenda.unlink(missing_ok=True)
    _systemctl("daemon-reload")


def test_agenda_cria_e_remove_o_timer(monkeypatch, tmp_path):
    if not lab_enabled():
        pytest.skip("HOMELAB_LAB=1 e root sao necessarios")
    agenda = tmp_path / "gitea-schedule.json"
    agent = load_agent(
        monkeypatch,
        {
            "SYSTEMD_DIR": "/etc/systemd/system",
            "GITEA_SCHEDULE": str(agenda),
            "GITEA_STATUS": str(tmp_path / "gitea.json"),
            "GITEA_BACKUP_DIR": str(tmp_path / "dumps"),
            "LOG_FILE": str(tmp_path / "agent.log"),
            "STORAGE_ROOT": "/tmp",
            "SNAPSHOT_ROOT": "/tmp/.snapshots",
            "ALLOWED_PATH_PREFIXES": "/tmp/",
            "SNAPSHOT_BACKEND": "none",
        },
    )
    _limpar(agenda)
    try:
        dados = agent.op_gitea_schedule_save(
            enabled=True, frequency="daily", time="05:00"
        )
        assert dados["on_calendar"] == "*-*-* 05:00:00"
        texto = UNIT.read_text()
        assert "OnCalendar=*-*-* 05:00:00" in texto
        assert f"Unit={SERVICO}" in texto
        assert _systemctl("is-enabled", TIMER).stdout.strip() == "enabled"
        assert _systemctl("is-active", TIMER).stdout.strip() == "active"
        assert _systemctl("is-active", SERVICO).stdout.strip() != "active"
        assert STAMP.is_file()

        agent.op_gitea_schedule_save(
            enabled=False, frequency="daily", time="05:00"
        )
        assert not UNIT.exists()
        assert _systemctl("is-enabled", TIMER).returncode != 0
        assert agenda.is_file()
    finally:
        _limpar(agenda)
