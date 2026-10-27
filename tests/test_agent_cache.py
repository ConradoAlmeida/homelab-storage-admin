from __future__ import annotations


def test_storage_overview_uses_cache_and_force_refreshes(agent_module, monkeypatch):
    agent = agent_module
    calls = []

    def collect():
        calls.append(len(calls) + 1)
        return {"marker": calls[-1], "disks": []}

    monkeypatch.setattr(agent, "_collect_storage_overview", collect)

    first = agent.op_storage_overview()
    assert first["marker"] == 1
    assert first["cache_age_seconds"] == 0
    assert first["stale"] is False

    second = agent.op_storage_overview()
    assert second["marker"] == 1
    assert calls == [1]

    forced = agent.op_storage_overview(force=True)
    assert forced["marker"] == 2
    assert calls == [1, 2]


def test_refresh_storage_bypasses_cache(agent_module, monkeypatch):
    agent = agent_module
    calls = []

    def collect():
        calls.append(len(calls) + 1)
        return {"marker": calls[-1], "disks": []}

    monkeypatch.setattr(agent, "_collect_storage_overview", collect)
    agent.op_storage_overview()
    refreshed = agent.op_refresh_storage()
    assert refreshed["marker"] == 2
    assert calls == [1, 2]
