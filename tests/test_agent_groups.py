from __future__ import annotations

import pytest


def setup_agent(agent, monkeypatch):
    monkeypatch.setattr(agent, "getent_group", lambda name: False)
    commands = []

    def fake_run(args, *args_, **kwargs):
        commands.append(list(args))
        return ""

    monkeypatch.setattr(agent, "run", fake_run)
    return commands


def test_create_group_auto_gid(agent_module, monkeypatch):
    agent = agent_module
    commands = setup_agent(agent, monkeypatch)
    result = agent.op_create_group("equipe")
    assert result == {"name": "equipe", "gid": None}
    assert commands == [["groupadd", "equipe"]]


def test_create_group_with_gid(agent_module, monkeypatch):
    agent = agent_module
    commands = setup_agent(agent, monkeypatch)
    monkeypatch.setattr(
        agent.grp,
        "getgrgid",
        lambda gid: (_ for _ in ()).throw(KeyError(gid)),
    )
    result = agent.op_create_group("equipe", 1500)
    assert result == {"name": "equipe", "gid": 1500}
    assert commands == [["groupadd", "-g", "1500", "equipe"]]


def test_create_group_rejects_reserved_invalid_and_existing(agent_module, monkeypatch):
    agent = agent_module
    setup_agent(agent, monkeypatch)
    with pytest.raises(agent.AgentError, match="reservado"):
        agent.op_create_group("root")
    with pytest.raises(agent.AgentError, match="invalido"):
        agent.op_create_group("Grupo Ruim")
    monkeypatch.setattr(agent, "getent_group", lambda name: True)
    with pytest.raises(agent.AgentError, match="ja existe"):
        agent.op_create_group("equipe")


def test_create_group_rejects_low_or_used_gid(agent_module, monkeypatch):
    agent = agent_module
    setup_agent(agent, monkeypatch)
    with pytest.raises(agent.AgentError, match="1000"):
        agent.op_create_group("equipe", 999)
    monkeypatch.setattr(agent.grp, "getgrgid", lambda gid: object())
    with pytest.raises(agent.AgentError, match="ja em uso"):
        agent.op_create_group("equipe", 1500)
