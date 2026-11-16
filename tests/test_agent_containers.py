from __future__ import annotations

import json

import pytest


def test_containers_overview_lista_e_ordena(agent_module, monkeypatch):
    agent = agent_module
    monkeypatch.setattr(agent, "_runtime_containers", lambda: "docker")

    def fake_run(args, timeout=15):
        if args[1] == "stats":
            return 0, "beta\t2.5%\t120MiB / 1GiB\t12.0%\n", ""
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
    assert beta["cpu_percent"] == 2.5
    assert beta["mem_used"] == "120.0 MiB"
    assert beta["mem_limit"] == "1.0 GiB"
    assert beta["mem_percent"] == 12.0
    assert beta["mem_bytes"] == 120 * 1024**2
    assert dados["stats_error"] == ""
    assert dados["stacks"] == [
        {
            "name": "web",
            "containers": 1,
            "running": 1,
            "cpu_percent": 2.5,
            "mem_bytes": 120 * 1024**2,
            "mem_used": "120.0 MiB",
        }
    ]


def test_containers_overview_sem_runtime(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_runtime_containers", lambda: "")
    dados = agent_module.op_containers_overview()
    assert dados["containers"] == []
    assert dados["stacks"] == []
    assert "Docker/Podman" in dados["error"]


def test_stats_podman_e_falha_nao_derrubam(agent_module, monkeypatch):
    agent = agent_module
    chamadas = []

    def fake_run(args, timeout=15):
        chamadas.append(args)
        return 0, "gitea\t0,5%\t1,5GB / 8GB\t18,75%\n", ""

    monkeypatch.setattr(agent, "run_optional", fake_run)
    stats, erro = agent._container_stats("podman", ["gitea"])
    assert erro == ""
    assert stats["gitea"]["cpu_percent"] == 0.5
    assert stats["gitea"]["mem_used"] == "1.4 GiB"
    assert stats["gitea"]["mem_limit"] == "7.5 GiB"
    assert stats["gitea"]["mem_percent"] == 18.8
    assert "{{.CPU}}" in chamadas[0][4]

    monkeypatch.setattr(
        agent, "run_optional", lambda args, timeout=15: (1, "", "sem permissao")
    )
    stats, erro = agent._container_stats("docker", ["gitea"])
    assert stats == {}
    assert "permissao" in erro


def test_stacks_agrupam_por_projeto_e_ignoram_avulsos(agent_module):
    stacks = agent_module._stacks_de_containers(
        [
            {"project": "web", "running": True, "cpu_percent": 1.0, "mem_bytes": 100},
            {"project": "web", "running": False, "cpu_percent": None, "mem_bytes": None},
            {"project": "", "running": True, "cpu_percent": 9.9, "mem_bytes": 999},
        ]
    )
    assert stacks == [
        {
            "name": "web",
            "containers": 2,
            "running": 1,
            "cpu_percent": 1.0,
            "mem_bytes": 100,
            "mem_used": "100 B",
        }
    ]


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
