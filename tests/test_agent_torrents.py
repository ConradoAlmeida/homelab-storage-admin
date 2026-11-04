from __future__ import annotations

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


def _lib_filmes(agent):
    bibliotecas = agent._bibliotecas_jellyfin()
    return next(item for item in bibliotecas if item["name"] == "Filmes")


def test_library_merge_renomeia_sem_destino(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, _series = preparar(agent, monkeypatch, tmp_path)
    midia = tmp_path / "midia"
    monkeypatch.setattr(agent, "ALLOWED_PATH_PREFIXES", (str(midia) + os.sep,))
    origem = filmes / "From (2022) Season 1"
    origem.mkdir()
    (origem / "capa.jpg").write_bytes(b"123")
    lib = _lib_filmes(agent)
    resultado = agent.op_library_merge_dir(
        library_id=lib["id"],
        source="From (2022) Season 1",
        dest="From (2022)",
    )
    assert resultado["ok"] is True
    assert (filmes / "From (2022)").is_dir()
    assert not origem.exists()


def test_library_merge_mescla_mesmo_tamanho(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, _series = preparar(agent, monkeypatch, tmp_path)
    midia = tmp_path / "midia"
    monkeypatch.setattr(agent, "ALLOWED_PATH_PREFIXES", (str(midia) + os.sep,))
    origem = filmes / "From (2022) Season 1"
    destino = filmes / "From (2022)"
    origem.mkdir()
    destino.mkdir()
    conteudo = b"mesmo"
    (origem / "capa.jpg").write_bytes(conteudo)
    (destino / "capa.jpg").write_bytes(conteudo)
    lib = _lib_filmes(agent)
    resultado = agent.op_library_merge_dir(
        library_id=lib["id"],
        source="From (2022) Season 1",
        dest="From (2022)",
    )
    assert resultado["ok"] is True
    assert not origem.exists()
    assert (destino / "capa.jpg").read_bytes() == conteudo


def test_library_merge_nao_sobrescreve_tamanho_diferente(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    filmes, _series = preparar(agent, monkeypatch, tmp_path)
    midia = tmp_path / "midia"
    monkeypatch.setattr(agent, "ALLOWED_PATH_PREFIXES", (str(midia) + os.sep,))
    origem = filmes / "Silo (2023) Season 1"
    destino = filmes / "Silo (2023)"
    origem.mkdir()
    destino.mkdir()
    (origem / "ep.mkv").write_bytes(b"novo")
    (destino / "ep.mkv").write_bytes(b"antigo")
    lib = _lib_filmes(agent)
    resultado = agent.op_library_merge_dir(
        library_id=lib["id"],
        source="Silo (2023) Season 1",
        dest="Silo (2023)",
    )
    assert resultado["ok"] is False
    assert "Arquivo diferente" in resultado["motivo"]
    assert (destino / "ep.mkv").read_bytes() == b"antigo"
    assert origem.exists()


def test_library_merge_recusa_caminho_invalido(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    preparar(agent, monkeypatch, tmp_path)
    lib = _lib_filmes(agent)
    with pytest.raises(agent.AgentError, match="invalido"):
        agent.op_library_merge_dir(
            library_id=lib["id"],
            source="../etc",
            dest="From (2022)",
        )


def test_library_merge_recusa_biblioteca_desconhecida(agent_module, monkeypatch, tmp_path):
    agent = agent_module
    preparar(agent, monkeypatch, tmp_path)
    with pytest.raises(agent.AgentError, match="Biblioteca invalida"):
        agent.op_library_merge_dir(
            library_id="nao-existe",
            source="A",
            dest="B",
        )
