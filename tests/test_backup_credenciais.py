from __future__ import annotations

import datetime as dt
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest


def _criar_banco(caminho: Path, valor: str = "original") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(str(caminho))
    try:
        conexao.execute("CREATE TABLE IF NOT EXISTS contas (nome TEXT)")
        conexao.execute("DELETE FROM contas")
        conexao.execute("INSERT INTO contas (nome) VALUES (?)", (valor,))
        conexao.commit()
    finally:
        conexao.close()


def _ler_banco(caminho: Path) -> str:
    conexao = sqlite3.connect(str(caminho))
    try:
        return conexao.execute("SELECT nome FROM contas").fetchone()[0]
    finally:
        conexao.close()


def _fontes(module) -> tuple[Path, Path]:
    return Path(module.CREDENCIAIS_DB), Path(module.CREDENCIAIS_ENV)


def test_run_gera_arquivo_com_banco_env_e_manifesto(agent_module):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CREDENTIALS_API_TOKEN=segredo\n")

    status = agent_module.op_credenciais_backup_run()

    destino = Path(agent_module.CREDENCIAIS_BACKUP_DIR)
    arquivo = destino / status["archive"]
    assert arquivo.is_file()
    assert status["ok"] is True
    with tarfile.open(arquivo, "r:gz") as pacote:
        nomes = sorted(pacote.getnames())
    assert nomes == [".env", "db.sqlite3", "manifest.json"]
    if os.name != "nt":
        assert arquivo.stat().st_mode & 0o777 == 0o600
        assert destino.stat().st_mode & 0o777 == 0o700


def test_verificacao_confere_integridade_e_hashes(agent_module):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=valor\n")

    status = agent_module.op_credenciais_backup_run()
    resultado = agent_module.op_credenciais_backup_verify(status["archive"])

    assert resultado["integrity"] == "ok"
    assert resultado["hashes_ok"] is True
    assert sorted(resultado["files"]) == [".env", "db.sqlite3"]


def test_retencao_remove_arquivo_antigo(agent_module):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=valor\n")
    destino = Path(agent_module.CREDENCIAIS_BACKUP_DIR)
    destino.mkdir(parents=True, exist_ok=True)
    antigo = destino / "moya-credenciais-20200101-033000.tar.gz"
    antigo.write_bytes(b"antigo")
    velho = (dt.datetime.now() - dt.timedelta(days=45)).timestamp()
    os.utime(antigo, (velho, velho))

    status = agent_module.op_credenciais_backup_run()

    assert antigo.name in status["removed"]
    assert not antigo.exists()


def test_retencao_remove_copia_de_restauracao_antiga(agent_module):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=valor\n")
    destino = Path(agent_module.CREDENCIAIS_BACKUP_DIR)
    antiga = destino / "pre-restore-20200101-000000"
    antiga.mkdir(parents=True)
    velho = (dt.datetime.now() - dt.timedelta(days=45)).timestamp()
    os.utime(antiga, (velho, velho))

    agent_module.op_credenciais_backup_run()

    assert not antiga.exists()


def test_overview_lista_fontes_e_arquivos(agent_module):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=valor\n")
    agent_module.op_credenciais_backup_run()

    dados = agent_module.op_credenciais_backup_overview()

    assert dados["available"] is True
    assert len(dados["archives"]) == 1
    assert dados["config"]["retention_days"] == 30
    assert dados["next_run"].endswith("03:30")


def test_overview_sem_fonte_nao_esta_disponivel(agent_module):
    dados = agent_module.op_credenciais_backup_overview()
    assert dados["available"] is False
    assert dados["archives"] == []


def test_restauracao_volta_banco_e_env(agent_module):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco, "antes")
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=antes\n")
    status = agent_module.op_credenciais_backup_run()

    _criar_banco(banco, "depois")
    ambiente.write_text("CHAVE=depois\n")

    resultado = agent_module.op_credenciais_backup_restore(
        status["archive"], restart=False
    )

    assert resultado["integrity"] == "ok"
    assert _ler_banco(banco) == "antes"
    assert ambiente.read_text() == "CHAVE=antes\n"
    anterior = Path(resultado["security_copy"])
    assert (anterior / "db.sqlite3").is_file()
    assert (anterior / ".env").is_file()


def _criar_extra(tmp_path: Path, valor: str = "extra") -> Path:
    caminho = tmp_path / "config" / "app.conf"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(valor + "\n")
    return caminho


def test_incluir_arquivo_individual_entra_no_proximo_backup(agent_module, tmp_path):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=valor\n")
    extra = _criar_extra(tmp_path)

    agent_module.op_credenciais_backup_add_file(str(extra))
    dados = agent_module.op_credenciais_backup_overview()
    assert str(extra) in dados["config"]["files"]
    assert any(item["path"] == str(extra) for item in dados["sources"])

    status = agent_module.op_credenciais_backup_run()
    with tarfile.open(
        Path(agent_module.CREDENCIAIS_BACKUP_DIR) / status["archive"], "r:gz"
    ) as pacote:
        nomes = pacote.getnames()
    assert f"files/0-{extra.name}" in nomes

    agent_module.op_credenciais_backup_remove_file(str(extra))
    assert agent_module.op_credenciais_backup_overview()["config"]["files"] == []


def test_restauracao_devolve_arquivo_individual(agent_module, tmp_path):
    banco, ambiente = _fontes(agent_module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=valor\n")
    extra = _criar_extra(tmp_path, "antes")
    agent_module.op_credenciais_backup_add_file(str(extra))
    status = agent_module.op_credenciais_backup_run()

    _criar_extra(tmp_path, "depois")
    resultado = agent_module.op_credenciais_backup_restore(
        status["archive"], restart=False
    )

    assert extra.read_text() == "antes\n"
    copia = Path(resultado["security_copy"]) / "files" / f"0-{extra.name}"
    assert copia.read_text() == "depois\n"


def test_incluir_recusa_diretorio_e_caminho_relativo(agent_module, tmp_path):
    with pytest.raises(agent_module.AgentError):
        agent_module.op_credenciais_backup_add_file("relativo.conf")
    with pytest.raises(agent_module.AgentError):
        agent_module.op_credenciais_backup_add_file(str(tmp_path / "config"))


def test_restauracao_recusa_nome_invalido(agent_module):
    with pytest.raises(agent_module.AgentError):
        agent_module.op_credenciais_backup_restore("../../etc/passwd", restart=False)


def test_run_falha_sem_banco(agent_module):
    with pytest.raises(agent_module.AgentError):
        agent_module.op_credenciais_backup_run()
