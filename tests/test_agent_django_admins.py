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
        if args[-1] == agent._DJANGO_ADMIN_PASSWORD_CODE:
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


def test_status_nao_aceita_app_fora_da_registry(agent_module, monkeypatch):
    _preparar(agent_module, monkeypatch)
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_status(app="moya-credenciais")
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_status(app="../../etc")


def test_status_marca_app_ausente_sem_derrubar_a_lista(agent_module, monkeypatch):
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


def test_create_envia_senha_por_stdin(agent_module, monkeypatch):
    mutacao = {
        "applied": True,
        "created": True,
        "weak": [],
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "superusers": ["admin", "conrado"],
    }
    chamadas = _preparar(agent_module, monkeypatch, mutacao=mutacao)
    dados = agent_module.op_django_admin_create(
        "credenciais", password="Senha-forte-123"
    )
    assert dados["applied"] is True
    assert dados["created"] is True
    assert dados["app"] == "credenciais"

    mutantes = [c for c in chamadas if c["args"][-1] == agent_module._DJANGO_ADMIN_PASSWORD_CODE]
    assert len(mutantes) == 1
    assert mutantes[0]["input"].strip() == "Senha-forte-123"
    assert "Senha-forte-123" not in " ".join(mutantes[0]["args"])
    assert "DJANGO_ADMIN_MODE=create" in mutantes[0]["args"]


def test_create_recusa_admin_existente(agent_module, monkeypatch):
    status = {
        **STATUS_VAZIO,
        "exists": True,
        "is_superuser": True,
        "usable_password": True,
        "superusers": ["admin"],
    }
    _preparar(agent_module, monkeypatch, status=status)
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_create("credenciais", password="x")


def test_senha_fraca_exige_confirmacao(agent_module, monkeypatch):
    mutacao = {
        "applied": False,
        "weak": ["This password is too short."],
        "created": False,
    }
    chamadas = _preparar(agent_module, monkeypatch, mutacao=mutacao)
    dados = agent_module.op_django_admin_create("credenciais", password="123")
    assert dados["applied"] is False
    assert dados["weak"]
    assert any("DJANGO_ADMIN_ALLOW_WEAK=0" in c["args"] for c in chamadas)


def test_senha_fraca_aplicada_com_confirmacao(agent_module, monkeypatch):
    mutacao = {
        "applied": True,
        "created": True,
        "weak": ["This password is too short."],
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "superusers": ["admin"],
    }
    chamadas = _preparar(agent_module, monkeypatch, mutacao=mutacao)
    dados = agent_module.op_django_admin_create(
        "credenciais", password="123", allow_weak=True
    )
    assert dados["applied"] is True
    assert dados["weak"]
    assert any("DJANGO_ADMIN_ALLOW_WEAK=1" in c["args"] for c in chamadas)


def test_set_password_de_admin_existente(agent_module, monkeypatch):
    status = {
        **STATUS_VAZIO,
        "exists": True,
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "superusers": ["admin", "conrado"],
    }
    mutacao = {
        "applied": True,
        "created": False,
        "weak": [],
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "superusers": ["admin", "conrado"],
    }
    chamadas = _preparar(agent_module, monkeypatch, status=status, mutacao=mutacao)
    dados = agent_module.op_django_admin_set_password(
        "storage", "conrado", "Nova-senha-123"
    )
    assert dados["applied"] is True
    assert dados["username"] == "conrado"
    mutantes = [c for c in chamadas if c["args"][-1] == agent_module._DJANGO_ADMIN_PASSWORD_CODE]
    assert len(mutantes) == 1
    assert "DJANGO_ADMIN_MODE=set" in mutantes[0]["args"]
    assert mutantes[0]["input"].strip() == "Nova-senha-123"


def test_set_password_exige_admin_existente(agent_module, monkeypatch):
    _preparar(agent_module, monkeypatch)
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_set_password("storage", "admin", "x")


def test_set_password_exige_superuser(agent_module, monkeypatch):
    status = {**STATUS_VAZIO, "exists": True, "is_superuser": False}
    _preparar(agent_module, monkeypatch, status=status)
    with pytest.raises(agent_module.AgentError):
        agent_module.op_django_admin_set_password("storage", "admin", "x")


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
    monkeypatch.setattr(agent_module.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
    monkeypatch.setattr(agent_module, "_fstype", lambda path: "ext4")
    monkeypatch.setattr(agent_module.os.path, "ismount", lambda path: False)
    caps = agent_module.host_capabilities()
    assert caps["django_admin"] is True

def _executar_codigo_de_senha(
    agent, monkeypatch, capsys, *, usuario, senha, modo, allow_weak=False
):
    import io
    import sys

    monkeypatch.setenv("DJANGO_ADMIN_USER", usuario)
    monkeypatch.setenv("DJANGO_ADMIN_EMAIL", "")
    monkeypatch.setenv("DJANGO_ADMIN_MODE", modo)
    monkeypatch.setenv("DJANGO_ADMIN_ALLOW_WEAK", "1" if allow_weak else "0")
    monkeypatch.setattr(sys, "stdin", io.StringIO(senha + "\n"))
    with pytest.raises(SystemExit):
        exec(agent._DJANGO_ADMIN_PASSWORD_CODE, {"__name__": "__main__"})
    saida = capsys.readouterr().out
    assert agent.DJANGO_ADMIN_MARKER in saida
    return json.loads(saida.split(agent.DJANGO_ADMIN_MARKER, 1)[1].strip())


@pytest.mark.django_db
def test_codigo_embutido_recusa_senha_fraca_sem_confirmacao(
    agent_module, monkeypatch, capsys
):
    from django.contrib.auth import get_user_model

    dados = _executar_codigo_de_senha(
        agent_module,
        monkeypatch,
        capsys,
        usuario="admin-teste",
        senha="123",
        modo="create",
    )
    assert dados["applied"] is False
    assert dados["weak"]
    assert not get_user_model().objects.filter(username="admin-teste").exists()


@pytest.mark.django_db
def test_codigo_embutido_cria_admin_com_senha_fraca_confirmada(
    agent_module, monkeypatch, capsys
):
    from django.contrib.auth import get_user_model

    dados = _executar_codigo_de_senha(
        agent_module,
        monkeypatch,
        capsys,
        usuario="admin-teste",
        senha="123",
        modo="create",
        allow_weak=True,
    )
    assert dados["applied"] is True
    assert dados["created"] is True
    user = get_user_model().objects.get(username="admin-teste")
    assert user.is_superuser and user.check_password("123")


@pytest.mark.django_db
def test_codigo_embutido_troca_senha_de_superuser_existente(
    agent_module, monkeypatch, capsys
):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_superuser(
        "conrado-teste", "conrado@moya.local", "senha-antiga"
    )
    dados = _executar_codigo_de_senha(
        agent_module,
        monkeypatch,
        capsys,
        usuario="conrado-teste",
        senha="Nova-senha-123",
        modo="set",
    )
    assert dados["applied"] is True
    assert dados["created"] is False
    user.refresh_from_db()
    assert user.check_password("Nova-senha-123")
    assert user.is_superuser
