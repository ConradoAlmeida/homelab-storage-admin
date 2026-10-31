from __future__ import annotations

import json
import os

import pytest


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


def cliente(agent, monkeypatch, info=None, posts=None):
    chamadas = []

    def abrir(method, path, data=None, timeout=20):
        chamadas.append((method, path, data))
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path == "/api/v2/torrents/info":
            return 200, json.dumps(info or [])
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info or [])
        if posts and path in posts:
            return posts[path]
        if path == "/api/v2/torrents/add":
            return 200, "Ok."
        return 200, "Ok."

    monkeypatch.setattr(agent, "_qbit_open", abrir)
    return chamadas


def test_bibliotecas_vem_das_pastas_do_jellyfin(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, series = preparar(agent, monkeypatch, tmp_path)
    bibliotecas = agent._bibliotecas_jellyfin()
    por_nome = {item["name"]: item["path"] for item in bibliotecas}
    assert por_nome == {
        "Filmes": os.path.realpath(filmes),
        "Séries": os.path.realpath(series),
    }


def test_url_do_qbittorrent_precisa_ser_localhost(agent_module):
    agent = agent_module
    agent.QBIT_URL = "http://203.0.113.10:8090"
    with pytest.raises(agent.AgentError, match="localhost"):
        agent._qbit_base()
    agent.QBIT_URL = "http://admin:segredo@127.0.0.1:8090"
    with pytest.raises(agent.AgentError, match="senha"):
        agent._qbit_base()


def test_add_so_aceita_magnet_e_pasta_conhecida(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, _series = preparar(agent, monkeypatch, tmp_path)
    chamadas = cliente(agent, monkeypatch)
    biblioteca = next(item for item in agent._bibliotecas_jellyfin() if item["name"] == "Filmes")
    magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=Filme"
    resultado = agent.op_torrent_add(magnet=magnet, library=biblioteca["id"])
    assert resultado["path"] == os.path.realpath(filmes)
    envio = next(item for item in chamadas if item[1] == "/api/v2/torrents/add")
    assert envio[2]["savepath"] == os.path.realpath(filmes)
    assert envio[2]["urls"] == magnet
    with pytest.raises(agent.AgentError, match="magnetico"):
        agent.op_torrent_add(magnet="https://example.test/filme.torrent", library=biblioteca["id"])
    with pytest.raises(agent.AgentError, match="Pasta"):
        agent.op_torrent_add(magnet=magnet, library="nao-existe")


def test_overview_esconde_torrent_fora_da_biblioteca(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, _series = preparar(agent, monkeypatch, tmp_path)
    dentro = "b" * 40
    cliente(
        agent,
        monkeypatch,
        info=[
            {
                "hash": dentro,
                "name": "Filme",
                "save_path": os.path.realpath(filmes),
                "progress": 0.5,
                "state": "downloading",
                "dlspeed": 1048576,
                "eta": 120,
                "size": 1024,
            },
            {
                "hash": "c" * 40,
                "name": "Outro",
                "save_path": "/tmp/fora",
                "progress": 1,
                "state": "stalledUP",
                "dlspeed": 0,
                "eta": 0,
                "size": 10,
            },
        ],
    )
    visao = agent.op_torrent_overview()
    assert [item["name"] for item in visao["torrents"]] == ["Filme"]
    assert visao["torrents"][0]["progress"] == 50
    assert visao["torrents"][0]["library"] == "Filmes"
    assert visao["active"] is True


def test_apagar_arquivos_recusa_torrent_fora_da_biblioteca(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    preparar(agent, monkeypatch, tmp_path)
    chamadas = cliente(
        agent,
        monkeypatch,
        info=[{"hash": "d" * 40, "save_path": "/tmp/fora", "state": "downloading"}],
    )
    with pytest.raises(agent.AgentError, match="nao esta"):
        agent.op_torrent_action(torrent_hash="d" * 40, action="delete_files")
    assert all(item[1] != "/api/v2/torrents/delete" for item in chamadas)


def test_apagar_arquivos_so_dentro_da_biblioteca(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, _series = preparar(agent, monkeypatch, tmp_path)
    chamadas = cliente(
        agent,
        monkeypatch,
        info=[{"hash": "e" * 40, "save_path": str(filmes), "state": "pausedDL"}],
    )
    agent.op_torrent_action(torrent_hash="e" * 40, action="delete_files")
    envio = next(item for item in chamadas if item[1] == "/api/v2/torrents/delete")
    assert envio[2]["deleteFiles"] == "true"
    assert envio[2]["hashes"] == "e" * 40


def test_pausar_usa_a_api_nova_e_a_antiga(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, _series = preparar(agent, monkeypatch, tmp_path)
    chamadas = []

    def abrir(method, path, data=None, timeout=20):
        chamadas.append(path)
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(
                [{"hash": "f" * 40, "save_path": str(filmes), "state": "downloading"}]
            )
        if path.endswith("/stop"):
            return 404, ""
        if path.endswith("/pause"):
            return 200, ""
        return 200, "Ok."

    monkeypatch.setattr(agent, "_qbit_open", abrir)
    agent.op_torrent_action(torrent_hash="f" * 40, action="pause")
    assert "/api/v2/torrents/stop" in chamadas
    assert "/api/v2/torrents/pause" in chamadas
