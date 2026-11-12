from __future__ import annotations

import pytest

def test_versoes_schedule_save_grava_cron(agent_module, tmp_path, monkeypatch):
    cron = tmp_path / "samba-snapshots"
    monkeypatch.setattr(agent_module, "VERSOES_CRON", str(cron))

    resultado = agent_module.op_versoes_schedule_save(hora_a="00:05", hora_b="12:05")

    assert resultado == {"hora_a": "00:05", "hora_b": "12:05"}
    texto = cron.read_text()
    assert "5 0,12 * * * root /usr/local/bin/samba-snapshot.sh" in texto


def test_versoes_schedule_save_recusa_horas_iguais(agent_module, tmp_path, monkeypatch):
    cron = tmp_path / "samba-snapshots"
    monkeypatch.setattr(agent_module, "VERSOES_CRON", str(cron))

    with pytest.raises(agent_module.AgentError, match="distint"):
        agent_module.op_versoes_schedule_save(hora_a="08:05", hora_b="08:05")


def test_versoes_schedule_save_recusa_minuto_invalido(agent_module, tmp_path, monkeypatch):
    cron = tmp_path / "samba-snapshots"
    monkeypatch.setattr(agent_module, "VERSOES_CRON", str(cron))

    with pytest.raises(agent_module.AgentError, match="HH:05"):
        agent_module.op_versoes_schedule_save(hora_a="00:10", hora_b="12:05")


def test_parse_versoes_schedule_line(agent_module):
    linha = "5 0,12 * * * root /usr/local/bin/samba-snapshot.sh"
    assert agent_module.parse_versoes_schedule_line(linha) == (0, 12)
    assert agent_module.parse_versoes_schedule_file(linha) == {
        "hora_a": "00:05",
        "hora_b": "12:05",
    }
