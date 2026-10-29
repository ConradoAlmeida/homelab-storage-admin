from __future__ import annotations

import json

import pytest


def test_containers_overview_lista_e_ordena(agent_module, monkeypatch):
    agent = agent_module
    monkeypatch.setattr(agent, "_runtime_containers", lambda: "docker")

    def fake_run(args, timeout=15):
        if args[1] == "ps" and "Status" in args[4]:
            return 0, "beta\tUp 2 hours\nalpha\tExited (0)\n", ""
        if args[1] == "ps":
            return 0, "beta\nalpha\n", ""
        if args[1] == "inspect":
            return (
                0,
                json.dumps(
                    [
                        {
                            "Name": "/beta",
                            "Id": "b" * 64,
                            "Config": {
                                "Image": "nginx:alpine",
                                "Labels": {
                                    "com.docker.compose.project": "web",
                                    "com.docker.compose.service": "proxy",
                                },
                            },
                            "State": {
                                "Status": "running",
                                "Running": True,
                                "Health": {"Status": "healthy"},
                                "RestartCount": 1,
                            },
                            "NetworkSettings": {
                                "Ports": {
                                    "80/tcp": [
                                        {"HostIp": "127.0.0.1", "HostPort": "8088"}
                                    ]
                                }
                            },
                        },
                        {
                            "Name": "/alpha",
                            "Id": "a" * 64,
                            "Config": {"Image": "alpine", "Labels": {}},
                            "State": {"Status": "exited", "Running": False},
                            "NetworkSettings": {"Ports": {}},
                        },
                    ]
                ),
                "",
            )
        return 1, "", ""

    monkeypatch.setattr(agent, "run_optional", fake_run)
    dados = agent.op_containers_overview()
    assert dados["runtime"] == "docker"
    assert dados["error"] == ""
    assert [item["name"] for item in dados["containers"]] == ["beta", "alpha"]
    beta = dados["containers"][0]
    assert beta["project"] == "web"
    assert beta["service"] == "proxy"
    assert beta["health"] == "healthy"
    assert beta["status"] == "Up 2 hours"
    assert beta["ports"] == ["127.0.0.1:8088->80/tcp"]


def test_containers_overview_sem_runtime(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_runtime_containers", lambda: "")
    dados = agent_module.op_containers_overview()
    assert dados["containers"] == []
    assert "Docker/Podman" in dados["error"]


def test_container_action_valida_nome_e_acao(agent_module, monkeypatch):
    agent = agent_module
    monkeypatch.setattr(agent, "_runtime_containers", lambda: "podman")
    monkeypatch.setattr(agent, "_nomes_containers", lambda runtime: ["gitea"])
    chamadas = []

    def fake_run(args, timeout=15):
        chamadas.append(args)
        return 0, "gitea\n", ""

    monkeypatch.setattr(agent, "run_optional", fake_run)
    dados = agent.op_container_action(name="gitea", action="stop")
    assert dados["action"] == "stop"
    assert chamadas[-1] == ["podman", "stop", "gitea"]

    with pytest.raises(agent.AgentError):
        agent.op_container_action(name="gitea", action="rm")
    with pytest.raises(agent.AgentError):
        agent.op_container_action(name="nao-existe", action="start")


def test_container_logs_limita_tail(agent_module, monkeypatch):
    agent = agent_module
    monkeypatch.setattr(agent, "_runtime_containers", lambda: "docker")
    monkeypatch.setattr(agent, "_nomes_containers", lambda runtime: ["gitea"])
    chamadas = []

    def fake_run(args, timeout=15):
        chamadas.append(args)
        return 0, "linha 1\nlinha 2\n", ""

    monkeypatch.setattr(agent, "run_optional", fake_run)
    dados = agent.op_container_logs(name="gitea", tail=99999)
    assert dados["tail"] == 1000
    assert "1000" in chamadas[-1]
    assert "linha 2" in dados["logs"]
