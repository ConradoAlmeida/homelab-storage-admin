from __future__ import annotations

import json
import os

import pytest

import core.qbittorrent as qbit
from core.agent import AgentError


def bibliotecas(filmes):
    return [
        {"id": "filmes", "name": "Filmes", "path": os.path.realpath(filmes)},
        {"id": "series", "name": "Séries", "path": "/mnt/jellyfin/series"},
    ]


def cliente(monkeypatch, info=None, posts=None):
    chamadas = []

    def abrir(method, path, data=None, timeout=20):
        chamadas.append((method, path, data))
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info or [])
        if posts and path in posts:
            return posts[path]
        if path == "/api/v2/torrents/add":
            return 200, "Ok."
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    return chamadas


def test_url_so_aceita_o_container_ou_localhost(monkeypatch):
    monkeypatch.setattr(qbit, "QBIT_URL", "http://203.0.113.10:8080")
    with pytest.raises(AgentError, match="container"):
        qbit._base()
    monkeypatch.setattr(qbit, "QBIT_URL", "http://admin:segredo@qbittorrent:8080")
    with pytest.raises(AgentError, match="senha"):
        qbit._base()
    monkeypatch.setattr(qbit, "QBIT_URL", "http://qbittorrent:8080")
    assert qbit._base() == "http://qbittorrent:8080"


def test_add_so_aceita_magnet_e_pasta_conhecida(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    chamadas = cliente(monkeypatch)
    pasta = bibliotecas(filmes)
    magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=Filme"
    resultado = qbit.adicionar(magnet, "filmes", pasta)
    assert resultado["path"] == os.path.realpath(filmes)
    envio = next(item for item in chamadas if item[1] == "/api/v2/torrents/add")
    assert envio[2]["savepath"] == os.path.realpath(filmes)
    assert envio[2]["urls"] == magnet
    assert envio[2]["autoTMM"] == "false"
    with pytest.raises(AgentError, match="magnético"):
        qbit.adicionar("https://example.test/filme.torrent", "filmes", pasta)
    with pytest.raises(AgentError, match="Pasta"):
        qbit.adicionar(magnet, "nao-existe", pasta)


def test_estado_esconde_torrent_fora_da_biblioteca(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    cliente(
        monkeypatch,
        info=[
            {
                "hash": "b" * 40,
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
    _client, torrents, erro = qbit.estado(bibliotecas(filmes))
    assert erro == ""
    assert [item["name"] for item in torrents] == ["Filme"]
    assert torrents[0]["progress"] == 50
    assert torrents[0]["library"] == "Filmes"
    assert torrents[0]["active"] is True
    assert torrents[0]["can_pause"] is True


def test_concluido_nao_oferece_pausar(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    cliente(
        monkeypatch,
        info=[
            {
                "hash": "a" * 40,
                "name": "Filme",
                "save_path": os.path.realpath(filmes),
                "progress": 1,
                "state": "stalledUP",
                "dlspeed": 0,
                "eta": 8640000,
                "size": 1024,
            }
        ],
    )
    _client, torrents, erro = qbit.estado(bibliotecas(filmes))
    assert erro == ""
    assert torrents[0]["state_label"] == "concluído"
    assert torrents[0]["can_pause"] is False
    assert torrents[0]["can_resume"] is False
    assert torrents[0]["speed"] == ""
    assert torrents[0]["eta"] == ""


def test_apagar_arquivos_recusa_torrent_fora_da_biblioteca(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    chamadas = cliente(
        monkeypatch,
        info=[{"hash": "d" * 40, "save_path": "/tmp/fora", "state": "downloading"}],
    )
    with pytest.raises(AgentError, match="não está"):
        qbit.acao("d" * 40, "delete_files", bibliotecas(filmes))
    assert all(item[1] != "/api/v2/torrents/delete" for item in chamadas)


def test_apagar_arquivos_so_dentro_da_biblioteca(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    chamadas = cliente(
        monkeypatch,
        info=[{"hash": "e" * 40, "save_path": str(filmes), "state": "pausedDL"}],
    )
    qbit.acao("e" * 40, "delete_files", bibliotecas(filmes))
    envio = next(item for item in chamadas if item[1] == "/api/v2/torrents/delete")
    assert envio[2]["deleteFiles"] == "true"
    assert envio[2]["hashes"] == "e" * 40


def test_pausar_usa_a_api_nova_e_a_antiga(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
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

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    qbit.acao("f" * 40, "pause", bibliotecas(filmes))
    assert "/api/v2/torrents/stop" in chamadas
    assert "/api/v2/torrents/pause" in chamadas
