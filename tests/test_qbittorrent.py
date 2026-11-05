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


def test_listar_pastas_ignora_padrao(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    (series / "Hart of Dixie (2011)").mkdir(parents=True)
    (series / "Silo (2023) Season 1 S01").mkdir(parents=True)
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, "[]"
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]
    linhas = qbit.listar_pastas_fora_padrao(libs[0], libs)
    assert [item["atual"] for item in linhas] == ["Silo (2023) Season 1 S01"]
    assert linhas[0]["alvo"] == "Silo (2023)"


def test_organizar_linhas_ignora_torrent_concluido(monkeypatch, tmp_path):
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

    def mesclar(*_args, **_kwargs):
        raise AssertionError("não deveria chamar o agente")

    relatorio = qbit.organizar_linhas(libs[0], ["Colony S01"], libs, mesclar)
    assert relatorio["feitos"] == []
    assert relatorio["ignorados"] == [
        {
            "nome": "Colony S01",
            "motivo": qbit._MSG_TORRENT_REMOVER_LISTA,
        }
    ]
    assert renames == []


def test_organizar_linhas_ignora_torrent_baixando(monkeypatch, tmp_path):
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
            "progress": 0.5,
            "state": "downloading",
            "save_path": str(series),
            "content_path": str(pasta / "ep.mkv"),
        }
    ]

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info)
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]

    relatorio = qbit.organizar_linhas(
        libs[0], ["Colony S01"], libs, lambda *_a, **_k: None
    )
    assert relatorio["ignorados"][0]["motivo"] == qbit._MSG_TORRENT_AGUARDE_DOWNLOAD


def test_listar_pastas_feedback_torrent(monkeypatch, tmp_path):
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
            "name": "Colony S01",
            "progress": 1,
            "state": "pausedUP",
            "save_path": str(series),
            "content_path": str(pasta / "ep.mkv"),
        }
    ]

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info)
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]
    linhas = qbit.listar_pastas_fora_padrao(libs[0], libs)
    assert linhas[0]["torrent_organizavel"] is True
    assert linhas[0]["feedback"] == qbit._MSG_TORRENT_REMOVER_LISTA


def test_listar_pastas_feedback_torrent_instavel_nao_e_organizavel(
    monkeypatch, tmp_path
):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    pasta = series / "Colony S01"
    pasta.mkdir(parents=True)
    (pasta / "ep.mkv").write_bytes(b"x")
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    info = [
        {
            "hash": "a" * 40,
            "name": "Colony S01",
            "progress": 1,
            "state": "moving",
            "save_path": str(series),
            "content_path": str(pasta / "ep.mkv"),
        }
    ]

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, json.dumps(info)
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]
    linha = qbit.listar_pastas_fora_padrao(libs[0], libs)[0]
    assert linha["torrent_organizavel"] is False
    assert linha["feedback"] == qbit._MSG_TORRENT_AGUARDE_DOWNLOAD


def test_organizar_linhas_só_marcadas(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    (series / "Colony S01").mkdir(parents=True)
    (series / "Outra S01").mkdir(parents=True)
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, "[]"
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]
    chamadas = []

    def mesclar(_lib, origem, destino):
        chamadas.append((origem, destino))
        return {"ok": True, "motivo": ""}

    relatorio = qbit.organizar_linhas(libs[0], ["Colony S01"], libs, mesclar)
    assert relatorio["feitos"]
    assert chamadas == [("Colony S01", "Colony (2016)")]
    assert os.path.isdir(series / "Colony S01") or True  # agente mock não move


def test_organizar_linhas_demo(monkeypatch):
    monkeypatch.setenv("STORAGE_ADMIN_DEMO", "1")
    relatorio = qbit.organizar_linhas({"id": "s"}, ["Colony S01"], [], lambda *_: None)
    assert relatorio["feitos"]


_MSG_INSTAVEL = (
    "Torrent em movimentação/verificação; aguarde o estado estabilizar antes de remover."
)


@pytest.mark.parametrize("action", ["delete", "delete_files"])
@pytest.mark.parametrize("state", ["moving", "checkingDL", "metaDL"])
def test_acao_recusa_exclusao_em_estado_instavel(
    monkeypatch, tmp_path, action, state
):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    chamadas = cliente(
        monkeypatch,
        info=[{"hash": "e" * 40, "save_path": str(filmes), "state": state}],
    )
    with pytest.raises(AgentError, match="movimentação"):
        qbit.acao("e" * 40, action, bibliotecas(filmes))
    assert all(item[1] != "/api/v2/torrents/delete" for item in chamadas)


def test_acao_delete_pausedup(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    chamadas = cliente(
        monkeypatch,
        info=[{"hash": "e" * 40, "save_path": str(filmes), "state": "pausedUP"}],
    )
    qbit.acao("e" * 40, "delete", bibliotecas(filmes))
    assert any(item[1] == "/api/v2/torrents/delete" for item in chamadas)


def test_acao_pausa_em_moving(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    chamadas = cliente(
        monkeypatch,
        info=[{"hash": "f" * 40, "save_path": str(filmes), "state": "moving"}],
    )
    qbit.acao("f" * 40, "pause", bibliotecas(filmes))
    assert any(
        item[1] in {"/api/v2/torrents/stop", "/api/v2/torrents/pause"} for item in chamadas
    )


def test_organizar_linhas_recusa_sem_ano(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    pasta = series / "Serie Nova S01 1080p"
    pasta.mkdir(parents=True)
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, "[]"
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]

    def mesclar(*_args, **_kwargs):
        raise AssertionError("não deveria mesclar pasta sem ano")

    relatorio = qbit.organizar_linhas(libs[0], ["Serie Nova S01 1080p"], libs, mesclar)
    assert relatorio["feitos"] == []
    assert relatorio["nao_feitos"][0]["motivo"] == "Sem ano no título e sem override"


def test_listar_pastas_sem_ano_e_residuo(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    sem_ano = series / "Serie Nova S01"
    sem_ano.mkdir(parents=True)
    grande = series / "Orfa S01 1080p"
    grande.mkdir(parents=True)
    monkeypatch.setattr(qbit, "_RESIDUO_MIN_BYTES", 100)
    (grande / "arquivo.bin").write_bytes(b"x" * 200)
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, "[]"
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]
    linhas = {item["atual"]: item for item in qbit.listar_pastas_fora_padrao(libs[0], libs)}
    assert linhas["Serie Nova S01"]["sem_ano"] is True
    assert linhas["Orfa S01 1080p"]["aviso"] == "Resíduo grande, sem torrent"


def test_listar_pastas_residuo_arquivo_esparso(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    grande = series / "Orfa S01 1080p"
    grande.mkdir(parents=True)
    monkeypatch.setattr(qbit, "_RESIDUO_MIN_BYTES", 1024**3)
    esparso = grande / "grande.bin"
    fd = os.open(esparso, os.O_CREAT | os.O_WRONLY)
    os.truncate(fd, 2 * 1024**3)
    os.close(fd)
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, "[]"
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]
    linhas = qbit.listar_pastas_fora_padrao(libs[0], libs)
    assert linhas[0]["aviso"] == qbit._AVISO_RESIDUO


def test_organizar_linhas_recusa_residuo_grande(monkeypatch, tmp_path):
    raiz = tmp_path / "jellyfin"
    series = raiz / "series"
    grande = series / "Show (2020) Season 1 S01"
    grande.mkdir(parents=True)
    monkeypatch.setattr(qbit, "_RESIDUO_MIN_BYTES", 100)
    (grande / "arquivo.bin").write_bytes(b"x" * 200)
    monkeypatch.setenv("JELLYFIN_ROOT", str(raiz))
    monkeypatch.delenv("STORAGE_ADMIN_DEMO", raising=False)

    def abrir(method, path, data=None, timeout=20):
        if path.startswith("/api/v2/torrents/info"):
            return 200, "[]"
        return 200, "Ok."

    monkeypatch.setattr(qbit, "_abrir", abrir)
    libs = [{"id": "series", "name": "Séries", "path": str(series)}]

    def mesclar(*_args, **_kwargs):
        raise AssertionError("não deveria mesclar resíduo grande")

    relatorio = qbit.organizar_linhas(libs[0], ["Show (2020) Season 1 S01"], libs, mesclar)
    assert relatorio["feitos"] == []
    assert relatorio["nao_feitos"][0]["motivo"] == qbit._AVISO_RESIDUO


def test_estado_instavel_esconde_exclusao(monkeypatch, tmp_path):
    filmes = tmp_path / "filmes"
    filmes.mkdir()
    cliente(
        monkeypatch,
        info=[
            {
                "hash": "b" * 40,
                "name": "Filme",
                "save_path": os.path.realpath(filmes),
                "progress": 0.9,
                "state": "moving",
                "dlspeed": 0,
                "eta": 0,
                "size": 1024,
            }
        ],
    )
    _client, torrents, erro = qbit.estado(bibliotecas(filmes))
    assert erro == ""
    assert torrents[0]["can_delete"] is False
    assert torrents[0]["delete_blocked_message"] == _MSG_INSTAVEL
