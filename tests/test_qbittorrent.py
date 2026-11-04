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
    assert envio[2]["category"] == "jellyfin"
    assert envio[2]["autoTMM"] == "false"
    with pytest.raises(AgentError, match="magnético"):
        qbit.adicionar("https://example.test/filme.torrent", "filmes", pasta)
    with pytest.raises(AgentError, match="Pasta"):
        qbit.adicionar(magnet, "nao-existe", pasta)


def test_add_duplicado_nao_reenvia(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    infohash = "ab" * 20
    chamadas = cliente(
        monkeypatch,
        info=[{"hash": infohash, "name": "Filme"}],
    )
    magnet = "magnet:?xt=urn:btih:" + infohash
    with pytest.raises(AgentError, match="já existe"):
        qbit.adicionar(magnet, "filmes", bibliotecas(filmes))
    assert all(item[1] != "/api/v2/torrents/add" for item in chamadas)


def test_add_fails_com_hash_na_lista_e_duplicata(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    infohash = "cd" * 20
    consultas = {"n": 0}

    def abrir(method, path, data=None, timeout=20):
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path.startswith("/api/v2/torrents/info"):
            consultas["n"] += 1
            if consultas["n"] == 1:
                return 200, "[]"
            return 200, json.dumps([{"hash": infohash}])
        if path == "/api/v2/torrents/add":
            return 200, "Fails."
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    magnet = "magnet:?xt=urn:btih:" + infohash
    with pytest.raises(AgentError, match="já existe"):
        qbit.adicionar(magnet, "filmes", bibliotecas(filmes))


def test_add_fails_sem_o_hash_continua_recusa(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    cliente(monkeypatch, info=[], posts={"/api/v2/torrents/add": (200, "Fails.")})
    magnet = "magnet:?xt=urn:btih:" + "ef" * 20
    with pytest.raises(AgentError, match="recusou"):
        qbit.adicionar(magnet, "filmes", bibliotecas(filmes))


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
    assert torrents[0]["download_speed"] == "1,0 MB/s"
    assert torrents[0]["download_bps"] == 1048576
    assert torrents[0]["size_bytes"] == 1024
    assert torrents[0]["upload_speed"] == "0 B/s"
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
                "upspeed": 0,
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
    assert torrents[0]["download_speed"] == "0 B/s"
    assert torrents[0]["upload_speed"] == "0 B/s"
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


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("Colony S01 1080p WEB-DL", "Colony (2016)"),
        ("www.exemplo.org Station Eleven S01", "Station Eleven (2021)"),
        ("Eternauta 1080p NF", "O Eternauta (2025)"),
        ("Filme Legal (2019) 720p BluRay", "Filme Legal (2019)"),
        ("Só o título sem ano", "Só o título sem ano"),
    ],
)
def test_alvo_da_pasta_limpa_titulo(bruto, esperado):
    assert qbit.alvo_da_pasta(bruto) == esperado


def test_alvo_da_pasta_sem_titulo():
    assert qbit.alvo_da_pasta("1080p WEB-DL") is None


def test_organizar_demo(monkeypatch):
    monkeypatch.setenv("STORAGE_ADMIN_DEMO", "1")
    relatorio = qbit.organizar([])
    assert relatorio["feitos"]
    assert relatorio["nao_feitos"]


def test_organizar_renomeia_concluido(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    pasta = series / "Colony S01"
    pasta.mkdir(parents=True)
    (pasta / "ep.mkv").write_bytes(b"x")
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    hash_ok = "a" * 40
    info = [
        {
            "hash": hash_ok,
            "name": "Colony S01 1080p",
            "category": "jellyfin",
            "progress": 1,
            "state": "stalledUP",
            "save_path": str(series),
            "content_path": str(pasta / "ep.mkv"),
        }
    ]
    renames = []

    def abrir(method, path, data=None, timeout=20):
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info)
        if path == "/api/v2/torrents/renameFolder":
            renames.append(data)
            return 200, "Ok."
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]
    relatorio = qbit.organizar(libs)
    assert relatorio["feitos"] == [{"de": "Colony S01", "para": "Colony (2016)"}]
    assert renames == [
        {"hash": hash_ok, "oldPath": "Colony S01", "newPath": "Colony (2016)"}
    ]


def test_organizar_ja_no_padrao(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    filmes = raiz / "filmes"
    destino = filmes / "Colony (2016)"
    destino.mkdir(parents=True)
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    info = [
        {
            "hash": "b" * 40,
            "name": "Colony S01 1080p",
            "category": "jellyfin",
            "progress": 1,
            "state": "stoppedUP",
            "save_path": str(filmes),
            "content_path": str(destino),
        }
    ]
    chamadas = []

    def abrir(method, path, data=None, timeout=20):
        chamadas.append(path)
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info)
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    relatorio = qbit.organizar(
        [{"id": "filmes", "name": "Filmes", "path": str(filmes)}]
    )
    assert relatorio["ja_no_padrao"] == ["Colony (2016)"]
    assert all("renameFolder" not in p for p in chamadas)


def test_organizar_nao_lista_fora_do_jellyfin(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    monkeypatch.setenv("JELLYFIN_ROOT", str(tmp_path / "jellyfin"))
    info = [
        {
            "hash": "c" * 40,
            "name": "Colony S01",
            "category": "jellyfin",
            "progress": 1,
            "state": "stalledUP",
            "save_path": str(filmes),
            "content_path": str(filmes / "Colony S01"),
        }
    ]
    listou = {"n": 0}
    real_listdir = os.listdir

    def listdir(path):
        listou["n"] += 1
        return real_listdir(path)

    monkeypatch.setattr(qbit.os, "listdir", listdir)

    def abrir(method, path, data=None, timeout=20):
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info)
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    relatorio = qbit.organizar(
        [{"id": "filmes", "name": "Filmes", "path": str(filmes)}]
    )
    assert listou["n"] == 0
    assert relatorio["nao_feitos"][0]["motivo"] == "Pasta fora do Jellyfin ou caminho inválido"


def test_organizar_pula_incompleto_e_categoria(monkeypatch, tmp_path):
    filmes = tmp_path / "jellyfin" / "filmes"
    filmes.mkdir(parents=True)
    monkeypatch.setenv("JELLYFIN_ROOT", str(tmp_path / "jellyfin"))
    info = [
        {
            "hash": "d" * 40,
            "name": "",
            "category": "jellyfin",
            "progress": 1,
            "state": "stalledUP",
            "save_path": str(filmes),
            "content_path": str(filmes / "x"),
        },
        {
            "hash": "e" * 40,
            "name": "Outro",
            "category": "outro",
            "progress": 1,
            "state": "stalledUP",
            "save_path": str(filmes),
            "content_path": str(filmes / "y"),
        },
        {
            "hash": "f" * 40,
            "name": "Baixando",
            "category": "jellyfin",
            "progress": 0.5,
            "state": "downloading",
            "save_path": str(filmes),
            "content_path": str(filmes / "z"),
        },
    ]

    def abrir(method, path, data=None, timeout=20):
        if path == "/api/v2/app/version":
            return 200, "v5.0.1"
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info)
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    relatorio = qbit.organizar(
        [{"id": "filmes", "name": "Filmes", "path": str(filmes)}]
    )
    assert relatorio["nao_feitos"][0]["motivo"] == "Sem título"
    assert len(relatorio["feitos"]) == 0
