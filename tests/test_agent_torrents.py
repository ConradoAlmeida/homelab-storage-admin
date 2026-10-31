from __future__ import annotations

import os


def preparar(agent, monkeypatch, tmp_path):
    config = tmp_path / "config"
    midia = tmp_path / "midia"
    filmes = midia / "filmes"
    series = midia / "series"
    filmes.mkdir(parents=True)
    series.mkdir(parents=True)
    for nome, caminho in (("Filmes", "/media/filmes"), ("Séries", "/media/series")):
        pasta = config / "root" / "default" / nome
        pasta.mkdir(parents=True)
        (pasta / "options.xml").write_text(
            "<LibraryOptions><PathInfos><MediaPathInfo>"
            f"<Path>{caminho}</Path>"
            "</MediaPathInfo></PathInfos></LibraryOptions>"
        )
    escapou = config / "root" / "default" / "Fora"
    escapou.mkdir()
    (escapou / "options.xml").write_text(
        "<LibraryOptions><PathInfos><MediaPathInfo>"
        "<Path>/media/../../etc</Path>"
        "</MediaPathInfo></PathInfos></LibraryOptions>"
    )
    config_lib = config / "root" / "default" / "Interna"
    config_lib.mkdir()
    (config_lib / "options.xml").write_text(
        "<LibraryOptions><PathInfos><MediaPathInfo>"
        "<Path>/config/root</Path>"
        "</MediaPathInfo></PathInfos></LibraryOptions>"
    )
    mounts = [
        {"source": str(config), "dest": "/config"},
        {"source": str(midia), "dest": "/media"},
    ]
    monkeypatch.setattr(agent, "_jellyfin_mounts", lambda: mounts)
    monkeypatch.setattr(agent, "_container_exists", lambda name: name == agent.JELLYFIN_CONTAINER)
    return filmes, series


def test_bibliotecas_vem_das_pastas_do_jellyfin(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, series = preparar(agent, monkeypatch, tmp_path)
    bibliotecas = agent._bibliotecas_jellyfin()
    por_nome = {item["name"]: item["path"] for item in bibliotecas}
    assert por_nome == {
        "Filmes": os.path.realpath(filmes),
        "Séries": os.path.realpath(series),
    }


def test_overview_so_devolve_as_pastas(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    preparar(agent, monkeypatch, tmp_path)
    visao = agent.op_torrent_overview()
    assert {item["name"] for item in visao["libraries"]} == {"Filmes", "Séries"}
    assert "client" not in visao
    assert "torrents" not in visao


def test_overview_sem_jellyfin(agent_module, monkeypatch):
    agent = agent_module
    monkeypatch.setattr(agent, "_container_exists", lambda name: False)
    visao = agent.op_torrent_overview()
    assert visao["libraries"] == []
    assert "Jellyfin" in visao["libraries_error"]
