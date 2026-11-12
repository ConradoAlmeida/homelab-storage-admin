from __future__ import annotations

import json

import pytest


STATUS_VAZIO = {
    "exists": False,
    "is_superuser": False,
    "is_staff": False,
    "is_active": False,
    "usable_password": False,
    "last_login": None,
    "date_joined": None,
    "superusers": ["conrado"],
}


def _saida(agent, dados):
    return (
        "21 objects imported automatically\n"
        + agent.DJANGO_ADMIN_MARKER
        + json.dumps(dados)
        + "\n"
    )


def _preparar(agent, monkeypatch, status=None, mutacao=None):
    monkeypatch.setattr(agent, "_runtime_containers", lambda: "docker")

    def fake_optional(args, timeout=15):
        assert args[1] == "inspect"
        return 0, "True\n", ""

    monkeypatch.setattr(agent, "run_optional", fake_optional)
    chamadas = []

    def fake_run(args, input_text=None, timeout=60):
        chamadas.append({"args": args, "input": input_text})
        if "get_or_create" in args[-1]:
            return _saida(agent, mutacao or {})
        return _saida(agent, status or STATUS_VAZIO)

    monkeypatch.setattr(agent, "run", fake_run)
    return chamadas


def test_status_lista_apps_da_registry(agent_module, monkeypatch):
    chamadas = _preparar(agent_module, monkeypatch)
    dados = agent_module.op_django_admin_status()
    assert [app["app"] for app in dados["apps"]] == [
        "credenciais",
        "storage",
        "datasheets",
        "drawings",
        "processos",
    ]
    assert all(app["installed"] for app in dados["apps"])
    assert all(app["running"] for app in dados["apps"])
    assert len(chamadas) == 5
    assert all("manage.py" in call["args"] for call in chamadas)


def test_status_nao_aceita_container_ou_app_fora_da_registry(
    agent_module, monkeypatch
):
    _preparar(agent_module, monkeypatch)
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_status(app="moya-credenciais")
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_status(app="../../etc")


def test_status_marca_app_ausente_sem_derrubar_a_lista(
    agent_module, monkeypatch
):
    monkeypatch.setattr(agent_module, "_runtime_containers", lambda: "docker")
    monkeypatch.setattr(
        agent_module,
        "run_optional",
        lambda args, timeout=15: (1, "", "no such container"),
    )
    dados = agent_module.op_django_admin_status(app="processos")
    app = dados["apps"][0]
    assert app["installed"] is False
    assert app["running"] is False
    assert "nao instalado" in app["error"]


def test_ensure_cria_com_senha_por_stdin(agent_module, monkeypatch):
    mutacao = {
        **STATUS_VAZIO,
        "exists": True,
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "created": True,
        "password_set": True,
        "promoted": False,
        "superusers": ["admin", "conrado"],
    }
    chamadas = _preparar(agent_module, monkeypatch, mutacao=mutacao)
    dados = agent_module.op_django_admin_ensure("credenciais")
    assert dados["created"] is True
    assert dados["password_set"] is True
    assert dados["password"]
    assert dados["app"] == "credenciais"

    mutantes = [c for c in chamadas if "get_or_create" in c["args"][-1]]
    assert len(mutantes) == 1
    chamada = mutantes[0]
    assert chamada["input"].strip() == dados["password"]
    assert dados["password"] not in " ".join(chamada["args"])
    assert "DJANGO_ADMIN_FORCE=1" in chamada["args"]


def test_ensure_preserva_senha_de_superuser_existente(
    agent_module, monkeypatch
):
    status = {
        **STATUS_VAZIO,
        "exists": True,
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "superusers": ["admin", "conrado"],
    }
    chamadas = _preparar(agent_module, monkeypatch, status=status)
    dados = agent_module.op_django_admin_ensure("credenciais")
    assert dados["created"] is False
    assert dados["password"] == ""
    assert not any("get_or_create" in c["args"][-1] for c in chamadas)


def test_ensure_promove_usuario_existente_com_senha_nova(
    agent_module, monkeypatch
):
    status = {
        **STATUS_VAZIO,
        "exists": True,
        "is_superuser": False,
        "is_staff": False,
        "is_active": True,
        "usable_password": True,
    }
    mutacao = {
        **status,
        "is_superuser": True,
        "is_staff": True,
        "created": False,
        "password_set": True,
        "promoted": True,
    }
    chamadas = _preparar(agent_module, monkeypatch, status=status, mutacao=mutacao)
    dados = agent_module.op_django_admin_ensure("storage")
    assert dados["password"]
    mutantes = [c for c in chamadas if "get_or_create" in c["args"][-1]]
    assert len(mutantes) == 1
    assert mutantes[0]["input"].strip() == dados["password"]
    assert "DJANGO_ADMIN_FORCE=1" in mutantes[0]["args"]


def test_rotate_exige_usuario_existente(agent_module, monkeypatch):
    _preparar(agent_module, monkeypatch)
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_rotate("credenciais")


def test_rotate_gera_nova_senha(agent_module, monkeypatch):
    status = {
        **STATUS_VAZIO,
        "exists": True,
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "superusers": ["admin"],
    }
    mutacao = {
        **status,
        "created": False,
        "password_set": True,
        "promoted": False,
    }
    chamadas = _preparar(agent_module, monkeypatch, status=status, mutacao=mutacao)
    dados = agent_module.op_django_admin_rotate("processos")
    assert dados["password"]
    mutantes = [c for c in chamadas if "get_or_create" in c["args"][-1]]
    assert len(mutantes) == 1
    assert dados["password"] not in " ".join(mutantes[0]["args"])
    assert "DJANGO_ADMIN_FORCE=1" in mutantes[0]["args"]


def test_usuario_invalido_e_recusado(agent_module, monkeypatch):
    _preparar(agent_module, monkeypatch)
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_status(username="admin; rm -rf /")


def test_capability_liga_quando_ha_app_instalado(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_runtime_containers", lambda: "docker")
    monkeypatch.setattr(
        agent_module,
        "_container_exists",
        lambda nome: nome == "moya-processos",
    )
    monkeypatch.setattr(agent_module, "shutil", agent_module.shutil)
    monkeypatch.setattr(agent_module.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
    monkeypatch.setattr(agent_module, "_fstype", lambda path: "ext4")
    monkeypatch.setattr(agent_module.os.path, "ismount", lambda path: False)
    caps = agent_module.host_capabilities()
    assert caps["django_admin"] is True
