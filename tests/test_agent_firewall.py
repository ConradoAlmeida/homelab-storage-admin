from __future__ import annotations

import pytest


def test_parse_ufw_rules_extrai_specs(agent_module):
    texto = """Added user rules (see 'ufw status' for running firewall):
ufw allow Samba
ufw allow 22/tcp
ufw allow from 192.168.0.0/24 to any port 8080 proto tcp
"""
    regras = agent_module._parse_ufw_rules(texto)
    assert [regra["spec"] for regra in regras] == [
        "allow Samba",
        "allow 22/tcp",
        "allow from 192.168.0.0/24 to any port 8080 proto tcp",
    ]
    assert regras[1]["to"] == "22/tcp"
    assert regras[2]["from"] == "192.168.0.0/24"
    assert regras[2]["to"] == "8080/tcp"
    assert agent_module._is_ssh_rule(regras[1]) is True
    assert agent_module._is_ssh_rule(regras[0]) is False


def test_ufw_default_policies(agent_module, tmp_path, monkeypatch):
    arquivo = tmp_path / "ufw"
    arquivo.write_text(
        'DEFAULT_INPUT_POLICY="DROP"\n'
        'DEFAULT_OUTPUT_POLICY="ACCEPT"\n'
        'DEFAULT_FORWARD_POLICY="DROP"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(agent_module, "UFW_DEFAULTS", str(arquivo))
    assert agent_module._ufw_default_policies() == {
        "incoming": "deny",
        "outgoing": "allow",
        "routed": "deny",
    }


def test_firewall_overview_le_regras_mesmo_inativo(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(agent_module, "UFW_DEFAULTS", "/nao/existe")

    def fake_optional(args, timeout=15):
        if args == ["ufw", "show", "added"]:
            return 0, "ufw allow 22/tcp\nufw allow 8080/tcp\n", ""
        if args == ["ufw", "status", "verbose"]:
            return 0, "Status: inactive\n", ""
        return 1, "", "erro"

    monkeypatch.setattr(agent_module, "run_optional", fake_optional)
    dados = agent_module.op_firewall_overview()
    assert dados["installed"] is True
    assert dados["active"] is False
    assert dados["status"] == "inativo"
    assert [regra["spec"] for regra in dados["rules"]] == [
        "allow 22/tcp",
        "allow 8080/tcp",
    ]
    assert dados["ssh_allowed"] is True


def test_firewall_overview_sem_ufw(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: False)
    dados = agent_module.op_firewall_overview()
    assert dados == {
        "installed": False,
        "active": False,
        "status": "indisponivel",
        "policies": {},
        "rules": [],
        "ssh_allowed": False,
        "error": "ufw nao esta instalado no host",
    }


def test_add_rule_monta_comando(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(agent_module, "_firewall_overview", lambda: {"rules": []})
    chamadas = []

    def fake_run(args, timeout=30):
        chamadas.append(args)
        return ""

    monkeypatch.setattr(agent_module, "run", fake_run)
    agent_module.op_firewall_add_rule(
        action="allow", port="8080", proto="tcp", source="192.168.0.0/24"
    )
    assert chamadas == [
        [
            "ufw",
            "allow",
            "from",
            "192.168.0.0/24",
            "to",
            "any",
            "port",
            "8080",
            "proto",
            "tcp",
        ]
    ]


def test_add_rule_sem_origem_e_proto_any(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(agent_module, "_firewall_overview", lambda: {"rules": []})
    chamadas = []
    monkeypatch.setattr(
        agent_module,
        "run",
        lambda args, timeout=30: chamadas.append(args) or "",
    )
    agent_module.op_firewall_add_rule(
        action="allow", port="80,443", proto="any", source=""
    )
    assert chamadas == [["ufw", "allow", "to", "any", "port", "80,443"]]


def test_add_rule_rejeita_entradas_invalidas(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(agent_module, "_firewall_overview", lambda: {"rules": []})
    monkeypatch.setattr(agent_module, "run", lambda args, timeout=30: "")

    with pytest.raises(agent_module.AgentError):
        agent_module.op_firewall_add_rule(action="drop", port="80")
    with pytest.raises(agent_module.AgentError):
        agent_module.op_firewall_add_rule(action="allow", port="abc")
    with pytest.raises(agent_module.AgentError):
        agent_module.op_firewall_add_rule(action="allow", port="80", source="nao-e-ip")
    with pytest.raises(agent_module.AgentError):
        agent_module.op_firewall_add_rule(action="deny", port="22", proto="tcp")


def test_ufw_public_listeners_ignora_loopback(agent_module, monkeypatch):
    def fake_optional(args, timeout=15):
        if args == ["ss", "-ltn"]:
            return (
                0,
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
                "LISTEN 0 4096 0.0.0.0:80 0.0.0.0:*\n"
                "LISTEN 0 4096 127.0.0.1:8060 0.0.0.0:*\n"
                "LISTEN 0 4096 [::]:443 [::]:*\n",
                "",
            )
        if args == ["ss", "-lun"]:
            return (
                0,
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
                "UNCONN 0 0 0.0.0.0:53 0.0.0.0:*\n",
                "",
            )
        return 1, "", ""

    monkeypatch.setattr(agent_module, "run_optional", fake_optional)
    assert agent_module._ufw_public_listeners() == {
        (80, "tcp"),
        (443, "tcp"),
        (53, "udp"),
    }


def test_ufw_public_listeners_perfil_pi(agent_module, monkeypatch):
    def fake_optional(args, timeout=15):
        if args == ["ss", "-ltn"]:
            return (
                0,
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
                "LISTEN 0 4096 192.168.0.150:8060 0.0.0.0:*\n"
                "LISTEN 0 4096 0.0.0.0:80 0.0.0.0:*\n"
                "LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*\n",
                "",
            )
        if args == ["ss", "-lun"]:
            return (
                0,
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
                "UNCONN 0 0 0.0.0.0:53 0.0.0.0:*\n",
                "",
            )
        return 1, "", ""

    monkeypatch.setattr(agent_module, "run_optional", fake_optional)
    assert agent_module._ufw_public_listeners() == {
        (8060, "tcp"),
        (80, "tcp"),
        (22, "tcp"),
        (53, "udp"),
    }


def test_ufw_rule_covers_perfis_conhecidos(agent_module):
    samba = {"action": "allow", "to": "Samba"}
    openssh = {"action": "allow", "to": "OpenSSH"}
    assert agent_module._ufw_rule_covers(samba, 445, "tcp") is True
    assert agent_module._ufw_rule_covers(samba, 137, "udp") is True
    assert agent_module._ufw_rule_covers(samba, 80, "tcp") is False
    assert agent_module._ufw_rule_covers(openssh, 22, "tcp") is True
    assert agent_module._ufw_rule_covers(openssh, 222, "tcp") is False


def test_enable_libera_portas_publicas_em_uso(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(
        agent_module,
        "_firewall_overview",
        lambda: {"active": False, "ssh_allowed": True, "rules": []},
    )
    monkeypatch.setattr(
        agent_module,
        "_ufw_public_listeners",
        lambda: {(80, "tcp"), (8060, "tcp")},
    )
    chamadas = []
    monkeypatch.setattr(
        agent_module,
        "run",
        lambda args, timeout=30: chamadas.append(args) or "",
    )
    agent_module.op_firewall_enable(allow_ssh=True)
    assert chamadas == [
        ["ufw", "allow", "80/tcp"],
        ["ufw", "allow", "8060/tcp"],
        ["ufw", "--force", "enable"],
    ]


def test_enable_nao_duplica_porta_ja_coberta(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(
        agent_module,
        "_firewall_overview",
        lambda: {
            "active": False,
            "ssh_allowed": True,
            "rules": [
                {
                    "action": "allow",
                    "to": "80/tcp",
                    "spec": "allow 80/tcp",
                    "signature": "allow 80/tcp",
                }
            ],
        },
    )
    monkeypatch.setattr(
        agent_module, "_ufw_public_listeners", lambda: {(80, "tcp")}
    )
    chamadas = []
    monkeypatch.setattr(
        agent_module,
        "run",
        lambda args, timeout=30: chamadas.append(args) or "",
    )
    agent_module.op_firewall_enable(allow_ssh=True)
    assert chamadas == [["ufw", "--force", "enable"]]


def test_enable_adiciona_ssh_quando_falta(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(
        agent_module,
        "_firewall_overview",
        lambda: {"active": False, "ssh_allowed": False, "rules": []},
    )
    monkeypatch.setattr(agent_module, "_ufw_public_listeners", lambda: set())
    chamadas = []
    monkeypatch.setattr(
        agent_module,
        "run",
        lambda args, timeout=30: chamadas.append(args) or "",
    )
    agent_module.op_firewall_enable(allow_ssh=True)
    assert chamadas == [
        ["ufw", "allow", "22/tcp"],
        ["ufw", "--force", "enable"],
    ]


def test_enable_recusa_sem_regra_ssh(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(
        agent_module,
        "_firewall_overview",
        lambda: {"active": False, "ssh_allowed": False, "rules": []},
    )
    with pytest.raises(agent_module.AgentError):
        agent_module.op_firewall_enable(allow_ssh=False)


def test_delete_ultima_regra_ssh_e_bloqueado(agent_module, monkeypatch):
    regra = {
        "signature": "allow 22/tcp",
        "action": "allow",
        "to": "22/tcp",
        "from": "Anywhere",
    }
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(
        agent_module,
        "_firewall_overview",
        lambda: {"active": True, "rules": [regra]},
    )
    chamadas = []
    monkeypatch.setattr(
        agent_module,
        "run",
        lambda args, timeout=30: chamadas.append(args) or "",
    )
    with pytest.raises(agent_module.AgentError):
        agent_module.op_firewall_delete_rule("allow 22/tcp")
    assert chamadas == []


def test_delete_recusa_spec_desatualizada(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(
        agent_module,
        "_firewall_overview",
        lambda: {
            "active": False,
            "rules": [
                {
                    "signature": "allow 8080/tcp",
                    "action": "allow",
                    "to": "8080/tcp",
                    "from": "Anywhere",
                }
            ],
        },
    )
    with pytest.raises(agent_module.AgentError):
        agent_module.op_firewall_delete_rule("allow 22/tcp")


def test_delete_perfil_repete_ate_remover_todas_as_partes(agent_module, monkeypatch):
    regra = {
        "signature": "allow Samba",
        "action": "allow",
        "to": "Samba",
        "from": "Anywhere",
    }
    estado = {"chamadas": 0}

    def overview():
        # Primeira leitura encontra a regra; cada remocao remove uma parte.
        estado["chamadas"] += 1
        if estado["chamadas"] <= 3:
            return {"active": False, "rules": [regra]}
        return {"active": False, "rules": []}

    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(agent_module, "_firewall_overview", overview)
    chamadas = []
    monkeypatch.setattr(
        agent_module,
        "run",
        lambda args, timeout=30: chamadas.append(args) or "",
    )
    agent_module.op_firewall_delete_rule("allow Samba")
    assert chamadas == [
        ["ufw", "--force", "delete", "allow", "Samba"],
        ["ufw", "--force", "delete", "allow", "Samba"],
    ]


def test_disable_desliga_ufw(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "_ufw_available", lambda: True)
    monkeypatch.setattr(
        agent_module,
        "_firewall_overview",
        lambda: {"active": True, "rules": []},
    )
    chamadas = []
    monkeypatch.setattr(
        agent_module,
        "run",
        lambda args, timeout=30: chamadas.append(args) or "",
    )
    agent_module.op_firewall_disable()
    assert chamadas == [["ufw", "--force", "disable"]]
