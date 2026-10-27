from __future__ import annotations


def test_live_metrics_is_hardware_only(agent_module, monkeypatch):
    agent = agent_module
    monkeypatch.setattr(
        agent,
        "_system_info",
        lambda: {
            "zones": [{"type": "cpu_thermal", "temp": 35.0}],
            "fans": [],
            "load": {"l1": 0.1, "l5": 0.2, "l15": 0.3},
            "cpu_percent": 5.0,
            "mem_total_mb": 1024,
            "mem_available_mb": 512,
        },
    )
    monkeypatch.setattr(
        agent,
        "op_df",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("nao deve ler discos")),
    )
    data = agent.op_live_metrics()
    assert data["system"]["cpu_percent"] == 5.0
    assert "disks" not in data
    assert "volumes" not in data
