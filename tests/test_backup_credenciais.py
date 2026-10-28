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


def _preparar(module) -> tuple[Path, Path]:
    banco, ambiente = _fontes(module)
    _criar_banco(banco)
    ambiente.parent.mkdir(parents=True, exist_ok=True)
    ambiente.write_text("CHAVE=valor\n")
    return banco, ambiente


def _job_padrao(module, **extra) -> dict:
    banco, ambiente = _fontes(module)
    job = {
        "name": "credenciais",
        "label": "Credenciais",
        "enabled": True,
        "time": "03:30",
        "frequency": "daily",
        "weekday": 0,
        "retention_days": 30,
        "sources": [
            {"kind": "sqlite", "path": str(banco)},
            {"kind": "env", "path": str(ambiente)},
        ],
    }
    job.update(extra)
    return job


def test_run_gera_arquivo_com_banco_env_e_manifesto(agent_module):
    _preparar(agent_module)

    status = agent_module._job_executar("credenciais")

    destino = Path(agent_module.CREDENCIAIS_BACKUP_DIR)
    arquivo = destino / status["archive"]
    assert arquivo.is_file()
    assert status["ok"] is True
    assert status["archive"].startswith("credenciais-")
    with tarfile.open(arquivo, "r:gz") as pacote:
        nomes = sorted(pacote.getnames())
    assert nomes == [".env", "db.sqlite3", "manifest.json"]
    if os.name != "nt":
        assert arquivo.stat().st_mode & 0o777 == 0o600
        assert destino.stat().st_mode & 0o777 == 0o700


def test_verificacao_confere_integridade_e_hashes(agent_module):
    _preparar(agent_module)
    status = agent_module._job_executar("credenciais")

    resultado = agent_module.op_arquivos_job_verify(
        "credenciais", status["archive"]
    )

    assert resultado["integrity"] == "ok"
    assert resultado["hashes_ok"] is True
    assert sorted(resultado["files"]) == [".env", "db.sqlite3"]


def test_retencao_remove_arquivo_antigo(agent_module):
    _preparar(agent_module)
    destino = Path(agent_module.CREDENCIAIS_BACKUP_DIR)
    destino.mkdir(parents=True, exist_ok=True)
    antigo = destino / "credenciais-20200101-033000.tar.gz"
    antigo.write_bytes(b"antigo")
    velho = (dt.datetime.now() - dt.timedelta(days=45)).timestamp()
    os.utime(antigo, (velho, velho))

    status = agent_module._job_executar("credenciais")

    assert antigo.name in status["removed"]
    assert not antigo.exists()


def test_retencao_remove_copia_de_restauracao_antiga(agent_module):
    _preparar(agent_module)
    destino = Path(agent_module.CREDENCIAIS_BACKUP_DIR)
    antiga = destino / "pre-restore-20200101-000000"
    antiga.mkdir(parents=True)
    velho = (dt.datetime.now() - dt.timedelta(days=45)).timestamp()
    os.utime(antiga, (velho, velho))

    agent_module._job_executar("credenciais")

    assert not antiga.exists()


def test_detalhe_lista_fontes_arquivos_e_agenda(agent_module):
    _preparar(agent_module)
    status = agent_module._job_executar("credenciais")

    dados = agent_module.op_arquivos_job("credenciais")

    assert dados["job"]["name"] == "credenciais"
    assert len(dados["sources"]) == 2
    assert dados["archives"][0]["name"] == status["archive"]
    assert dados["agenda"] == "diário 03:30"
    assert dados["next_run"].endswith("03:30")


def test_fonte_ausente_impede_o_backup(agent_module):
    banco, _ = _fontes(agent_module)
    banco.unlink(missing_ok=True)
    with pytest.raises(agent_module.AgentError):
        agent_module._job_executar("credenciais")


def test_restauracao_volta_banco_e_env(agent_module):
    banco, ambiente = _preparar(agent_module)
    banco_original = _ler_banco(banco)
    status = agent_module._job_executar("credenciais")

    _criar_banco(banco, "depois")
    ambiente.write_text("CHAVE=depois\n")

    resultado = agent_module.op_arquivos_job_restore(
        "credenciais", status["archive"], restart=False
    )

    assert resultado["integrity"] == "ok"
    assert _ler_banco(banco) == banco_original
    assert ambiente.read_text() == "CHAVE=valor\n"
    anterior = Path(resultado["security_copy"])
    assert (anterior / "db.sqlite3").is_file()
    assert (anterior / ".env").is_file()


def test_incluir_arquivo_individual_entra_no_proximo_backup(agent_module, tmp_path):
    _preparar(agent_module)
    extra = tmp_path / "config" / "app.conf"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("extra\n")

    agent_module.op_credenciais_backup_add_file(str(extra))
    dados = agent_module.op_credenciais_backup_overview()
    assert any(item["path"] == str(extra) for item in dados["sources"])

    status = agent_module._job_executar("credenciais")
    with tarfile.open(
        Path(agent_module.CREDENCIAIS_BACKUP_DIR) / status["archive"], "r:gz"
    ) as pacote:
        nomes = pacote.getnames()
    assert "files/0-app.conf" in nomes

    agent_module.op_credenciais_backup_remove_file(str(extra))
    dados = agent_module.op_credenciais_backup_overview()
    assert all(item["path"] != str(extra) for item in dados["sources"])


def test_incluir_pasta_backup_e_restore(agent_module, tmp_path):
    _preparar(agent_module)
    pasta = tmp_path / "projeto"
    (pasta / "sub").mkdir(parents=True)
    (pasta / "raiz.txt").write_text("raiz\n")
    (pasta / "sub" / "item.txt").write_text("item\n")
    (pasta / "vazia").mkdir()
    agent_module.op_credenciais_backup_add_file(str(pasta))

    status = agent_module._job_executar("credenciais")
    with tarfile.open(
        Path(agent_module.CREDENCIAIS_BACKUP_DIR) / status["archive"], "r:gz"
    ) as pacote:
        nomes = pacote.getnames()
    assert "files/0-projeto/raiz.txt" in nomes
    assert "files/0-projeto/sub/item.txt" in nomes
    assert "files/0-projeto/vazia" in nomes
    assert len(nomes) == len(set(nomes))

    (pasta / "raiz.txt").write_text("alterado\n")
    (pasta / "novo.txt").write_text("novo\n")
    resultado = agent_module.op_arquivos_job_restore(
        "credenciais", status["archive"], restart=False
    )
    assert (pasta / "raiz.txt").read_text() == "raiz\n"
    assert (pasta / "sub" / "item.txt").read_text() == "item\n"
    assert (pasta / "vazia").is_dir()
    assert (pasta / "novo.txt").read_text() == "novo\n"
    copia = Path(resultado["security_copy"]) / "files/0-projeto/raiz.txt"
    assert copia.read_text() == "alterado\n"


def test_agendamento_semanal_e_retencao(agent_module):
    _preparar(agent_module)

    dados = agent_module.op_credenciais_backup_settings(
        time="04:15", frequency="weekly", weekday=2, retention_days=60
    )

    assert dados["job"]["time"] == "04:15"
    assert dados["job"]["frequency"] == "weekly"
    assert dados["job"]["retention_days"] == 60
    assert dados["agenda"] == "semanal (quarta) 04:15"
    assert dados["next_run"]


def test_incluir_recusa_caminho_relativo_e_proibido(agent_module):
    with pytest.raises(agent_module.AgentError):
        agent_module.op_credenciais_backup_add_file("relativo.conf")
    with pytest.raises(agent_module.AgentError):
        agent_module.op_credenciais_backup_add_file("/proc/version")


def test_dois_jobs_com_agendas_e_arquivos_independentes(agent_module, tmp_path):
    _preparar(agent_module)
    semanal = tmp_path / "documentos"
    semanal.mkdir()
    (semanal / "a.txt").write_text("a\n")

    agent_module.op_arquivos_job_save(
        {
            "name": "documentos",
            "label": "Documentos",
            "enabled": True,
            "time": "05:00",
            "frequency": "weekly",
            "weekday": 4,
            "retention_days": 12,
            "sources": [{"path": str(semanal)}],
        }
    )
    config = agent_module._jobs_config()
    nomes = [job["name"] for job in config["jobs"]]
    assert nomes == ["credenciais", "documentos"]

    status_cred = agent_module._job_executar("credenciais")
    status_doc = agent_module._job_executar("documentos")
    assert status_cred["archive"].startswith("credenciais-")
    assert status_doc["archive"].startswith("documentos-")

    detalhe = agent_module.op_arquivos_job("documentos")
    assert detalhe["job"]["retention_days"] == 12
    assert detalhe["agenda"] == "semanal (sexta) 05:00"
    assert [item["name"] for item in detalhe["archives"]] == [status_doc["archive"]]

    cred = agent_module.op_arquivos_job("credenciais")
    assert status_doc["archive"] not in [item["name"] for item in cred["archives"]]
    assert status_cred["archive"] in [item["name"] for item in cred["archives"]]

    agent_module.op_arquivos_job_delete("documentos")
    nomes = [job["name"] for job in agent_module._jobs_config()["jobs"]]
    assert nomes == ["credenciais"]


def test_disk_setup_recusa_disco_do_sistema(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    disco = {
        "path": "/dev/sda",
        "name": "sda",
        "candidate": False,
        "system": True,
        "mounts": ["/"],
        "reason": "disco do sistema",
        "extra_confirmation": False,
        "required_phrase": "FORMATAR /dev/sda",
    }
    monkeypatch.setattr(agent_module, "_backup_disks", lambda config: [disco])
    monkeypatch.setattr(
        agent_module, "_load_backup_config", lambda: {"disks": [], "jobs": []}
    )
    with pytest.raises(agent_module.AgentError, match="disco do sistema"):
        agent_module.op_backup_disk_setup("/dev/sda", "backup", "FORMATAR /dev/sda")


def test_health_do_repositorio_ida_e_volta(agent_module, monkeypatch, tmp_path):
    monkeypatch.setattr(agent_module, "BACKUP_HEALTH_DIR", str(tmp_path))
    agent_module._backup_health_write(
        "uuid-1", {"ok": True, "finished_at": "2026-10-28T04:30:00"}
    )
    dados = agent_module._backup_health_read("uuid-1")
    assert dados["ok"] is True
    assert dados["finished_at"] == "2026-10-28T04:30:00"
    if os.name != "nt":
        assert (tmp_path / "uuid-1.json").stat().st_mode & 0o777 == 0o600


def test_job_copia_sqlite_com_backup_api(agent_module, tmp_path):
    pasta = tmp_path / "dados"
    pasta.mkdir()
    _criar_banco(pasta / "app.db", "valor")
    (pasta / "leiame.txt").write_text("ok\n")
    agent_module.op_arquivos_job_save(
        {
            "name": "apps",
            "label": "Apps",
            "enabled": False,
            "time": "03:30",
            "frequency": "daily",
            "weekday": 0,
            "retention_days": 7,
            "sources": [{"path": str(pasta)}],
        }
    )
    status = agent_module._job_executar("apps")
    destino = tmp_path / "extraido"
    destino.mkdir()
    with tarfile.open(
        Path(agent_module.CREDENCIAIS_BACKUP_DIR) / status["archive"], "r:gz"
    ) as pacote:
        pacote.extractall(destino, filter="data")
    copia = destino / "files/0-dados/app.db"
    assert _ler_banco(copia) == "valor"


def test_job_backup_para_usb_com_hash(agent_module, monkeypatch, tmp_path):
    pasta = tmp_path / "dados"
    pasta.mkdir()
    (pasta / "arquivo.txt").write_text("conteudo\n")
    agent_module.op_arquivos_job_save(
        {
            "name": "apps",
            "label": "Apps",
            "enabled": False,
            "time": "03:30",
            "frequency": "daily",
            "weekday": 0,
            "retention_days": 7,
            "sources": [{"path": str(pasta)}],
        }
    )
    usb = tmp_path / "usb"
    usb.mkdir()
    monkeypatch.setattr(
        agent_module,
        "_gitea_usb_disks",
        lambda: [{"name": "sdb", "path": "/dev/sdb", "has_filesystem": True}],
    )
    monkeypatch.setattr(
        agent_module, "_usb_montar", lambda disco: (usb, False)
    )
    monkeypatch.setattr(agent_module, "_usb_desmontar", lambda *a: None)

    resultado = agent_module.op_arquivos_job_usb_backup("apps", "sdb")

    arquivo = usb / "apps" / "apps" / resultado["archive"]
    assert arquivo.is_file()
    assert resultado["verified"] is True
    sidecar = usb / "apps" / "apps" / f"{resultado['archive']}.sha256"
    assert resultado["sha256"] in sidecar.read_text()
