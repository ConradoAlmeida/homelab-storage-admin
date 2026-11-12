from __future__ import annotations

import json

import pytest


def _preparar(agent_module, tmp_path, monkeypatch, cron_text=None):
    cron = tmp_path / "samba-snapshots"
    if cron_text is not None:
        cron.write_text(cron_text, encoding="utf-8")
    monkeypatch.setattr(agent_module, "VERSOES_CRON", str(cron))
    monkeypatch.setattr(
        agent_module,
        "SNAPSHOT_SCHEDULE",
        str(tmp_path / "snapshot-schedule.json"),
    )
    monkeypatch.setattr(
        agent_module, "run_optional", lambda *args, **kwargs: (0, "", "")
    )
    return cron


def test_snapshot_times_uma_por_dia(agent_module):
    assert agent_module._snapshot_times(1, "03:00") == ["03:00"]


def test_snapshot_times_quatro_por_dia(agent_module):
    assert agent_module._snapshot_times(4, "00:05") == [
        "00:05",
        "06:05",
        "12:05",
        "18:05",
    ]


def test_snapshot_times_duas_por_dia(agent_module):
    assert agent_module._snapshot_times(2, "00:05") == ["00:05", "12:05"]


def test_snapshot_schedule_label(agent_module):
    assert agent_module._snapshot_schedule_label(["03:00"]) == "1×/dia às 03:00"
    assert (
        agent_module._snapshot_schedule_label(["00:05", "12:05"])
        == "2×/dia às 00:05 e 12:05"
    )


def test_versoes_schedule_save_grava_json_e_timer(agent_module, tmp_path, monkeypatch):
    cron = _preparar(
        agent_module,
        tmp_path,
        monkeypatch,
        "# snapshots\n5 0,12 * * * root /usr/local/bin/samba-snapshot.sh\n",
    )

    resultado = agent_module.op_versoes_schedule_save(
        per_day="4", first_time="00:05"
    )

    assert resultado["per_day"] == 4
    assert resultado["times"] == ["00:05", "06:05", "12:05", "18:05"]
    dados = json.loads((tmp_path / "snapshot-schedule.json").read_text())
    assert dados == {"per_day": 4, "first_time": "00:05"}
    timer = (tmp_path / "systemd" / "homelab-storage-snapshot.timer").read_text()
    assert "OnCalendar=*-*-* 00:05:00" in timer
    assert "OnCalendar=*-*-* 18:05:00" in timer
    assert "4x/dia" in timer
    assert not cron.exists()


def test_versoes_schedule_save_aceita_uma_por_dia(agent_module, tmp_path, monkeypatch):
    _preparar(agent_module, tmp_path, monkeypatch)

    resultado = agent_module.op_versoes_schedule_save(
        per_day="1", first_time="03:00"
    )

    assert resultado["times"] == ["03:00"]
    timer = (tmp_path / "systemd" / "homelab-storage-snapshot.timer").read_text()
    assert timer.count("OnCalendar=") == 1


def test_versoes_schedule_save_recusa_fora_da_faixa(agent_module, tmp_path, monkeypatch):
    _preparar(agent_module, tmp_path, monkeypatch)

    with pytest.raises(agent_module.AgentError, match="entre 1 e 24"):
        agent_module.op_versoes_schedule_save(per_day="0", first_time="00:05")
    with pytest.raises(agent_module.AgentError, match="entre 1 e 24"):
        agent_module.op_versoes_schedule_save(per_day="25", first_time="00:05")


def test_versoes_schedule_save_recusa_horario_invalido(
    agent_module, tmp_path, monkeypatch
):
    _preparar(agent_module, tmp_path, monkeypatch)

    with pytest.raises(agent_module.AgentError, match="HH:MM"):
        agent_module.op_versoes_schedule_save(per_day="2", first_time="25:00")


def test_versoes_schedule_save_compatibilidade_dois_horarios(
    agent_module, tmp_path, monkeypatch
):
    _preparar(agent_module, tmp_path, monkeypatch)

    resultado = agent_module.op_versoes_schedule_save(
        hora_a="12:05", hora_b="00:05"
    )

    assert resultado["per_day"] == 2
    assert resultado["first_time"] == "00:05"


def test_reconcile_migra_cron_legado(agent_module, tmp_path, monkeypatch):
    cron = _preparar(
        agent_module,
        tmp_path,
        monkeypatch,
        "# versoes_snapshots\n5 0,12 * * * root /usr/local/bin/samba-snapshot.sh\n",
    )

    dados = agent_module._reconcile_snapshot_schedule()

    assert dados["per_day"] == 2
    assert dados["times"] == ["00:05", "12:05"]
    assert not cron.exists()
    assert (tmp_path / "snapshot-schedule.json").is_file()


def test_parse_versoes_schedule_line(agent_module):
    linha = "5 0,12 * * * root /usr/local/bin/samba-snapshot.sh"
    assert agent_module.parse_versoes_schedule_line(linha) == (0, 12)
    assert agent_module.parse_versoes_schedule_file(linha) == {
        "hora_a": "00:05",
        "hora_b": "12:05",
    }
