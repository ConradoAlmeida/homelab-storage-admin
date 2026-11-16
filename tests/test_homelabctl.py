from __future__ import annotations

import subprocess
import sys

from .conftest import ROOT

CLI = ROOT / "scripts" / "homelabctl.py"


def rodar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )


def test_list_mostra_os_dois_hosts():
    resultado = rodar("list")
    assert resultado.returncode == 0, resultado.stderr
    linhas = resultado.stdout.splitlines()
    assert any(linha.startswith("pi ") for linha in linhas)
    assert any(linha.startswith("moya ") for linha in linhas)


def test_check_valida_todos():
    resultado = rodar("check")
    assert resultado.returncode == 0, resultado.stderr
    assert "ok pi" in resultado.stdout
    assert "ok moya" in resultado.stdout
    assert "credenciais" in resultado.stdout  # feature listada no resumo


def test_check_falha_com_config_ruim(tmp_path, monkeypatch):
    # Um host quebrado no diretorio de hosts tem que derrubar o check.
    import shutil

    destino = tmp_path / "hosts"
    shutil.copytree(ROOT / "hosts", destino)
    (destino / "quebrado").mkdir()
    (destino / "quebrado" / "host.toml").write_text('[host]\nnome = "quebrado"\n')

    codigo = (
        "import sys; from pathlib import Path;"
        f"sys.path.insert(0, {str(ROOT)!r});"
        "import core.homelab_config as c;"
        f"c.DIR_HOSTS = Path({str(destino)!r});"
        f"sys.argv = ['homelabctl', 'check'];"
        "import runpy; runpy.run_path(" + repr(str(CLI)) + ", run_name='__main__')"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, cwd=ROOT
    )
    assert resultado.returncode == 2 or resultado.returncode == 1
    assert "quebrado" in resultado.stderr


def test_render_pi_imprime_o_host_env():
    resultado = rodar("render", "pi")
    assert resultado.returncode == 0, resultado.stderr
    assert 'SITE_NAME="Homelab Storage"' in resultado.stdout
    assert "HOST_PROFILE=pi" in resultado.stdout
    assert (
        "APPS_ENV_PATH=/opt/stacks/homelab-storage-admin/deploy/pi/apps.env"
        in resultado.stdout
    )
    assert "Gerado por homelabctl render" in resultado.stdout


def test_render_sync_do_moya():
    resultado = rodar("render", "moya", "--sync")
    assert resultado.returncode == 0, resultado.stderr
    assert "CADDY_PORTA=:80" in resultado.stdout
    assert "UPSTREAM_HOST=localhost" in resultado.stdout


def test_render_write_grava_e_faz_backup(tmp_path):
    primeira = rodar("render", "pi", "--write", "--ambos", "--destino", str(tmp_path))
    assert primeira.returncode == 0, primeira.stderr
    host_env = tmp_path / "host.env"
    assert host_env.is_file()
    assert (tmp_path / "sync.env").is_file()
    assert oct(host_env.stat().st_mode & 0o777) == "0o644"

    segunda = rodar("render", "pi", "--write", "--destino", str(tmp_path))
    assert segunda.returncode == 0, segunda.stderr
    assert "sem mudanca" in segunda.stdout
    # Sem mudanca nao cria backup a mais.
    assert not list(tmp_path.glob("host.env.bak-*"))


def test_render_host_inexistente_erra():
    resultado = rodar("render", "naoexiste")
    assert resultado.returncode == 2
    assert "naoexiste" in resultado.stderr


def test_requisitos_lista_binarios_do_host():
    resultado = rodar("requisitos", "moya")
    assert resultado.returncode == 0, resultado.stderr
    linhas = resultado.stdout.splitlines()
    assert "obrig|pdbedit|samba samba-common-bin" in linhas
    assert any(linha.startswith("opc|btrfs|") for linha in linhas)
    # Um binario por linha, sem repetir entre features.
    nomes = [linha.split("|")[1] for linha in linhas]
    assert len(nomes) == len(set(nomes))


def test_render_poda_backups_antigos(tmp_path):
    # /etc com um .bak por render vira lixo; so os tres mais novos ficam.
    alvo = tmp_path / "host.env"
    alvo.write_text("# antigo\n", encoding="utf-8")
    for dia in range(1, 6):
        (tmp_path / f"host.env.bak-2020010{dia}-000000").write_text("x", encoding="utf-8")

    resultado = rodar("render", "pi", "--write", "--destino", str(tmp_path))
    assert resultado.returncode == 0, resultado.stderr
    backups = sorted(tmp_path.glob("host.env.bak-*"))
    assert len(backups) == 3
    # Os antigos de 2020 sairam; o novo e o da execucao.
    assert not any("20200101" in b.name for b in backups)
    assert len([b for b in backups if "2020010" in b.name]) == 2


def test_boot_grava_a_unit_no_destino(tmp_path):
    resultado = rodar("boot", "pi", "--write", "--destino", str(tmp_path))
    assert resultado.returncode == 0, resultado.stderr
    unidade = tmp_path / "homelab-compose.service"
    assert unidade.is_file()
    assert "ExecStart=/bin/sh -c 'until ip -4 addr show" in unidade.read_text()


def test_doctor_aponta_o_que_falta(tmp_path):
    resultado = rodar("doctor", "pi", "--config-dir", str(tmp_path))
    assert resultado.returncode == 1
    assert "erro: falta host.env" in resultado.stdout
    assert "render pi --write" in resultado.stdout
    assert "erros:" in resultado.stdout


def test_bootstrap_sim_nao_escreve_nada(tmp_path):
    config = tmp_path / "etc"
    env = tmp_path / "container.env"
    resultado = rodar(
        "bootstrap", "pi", "--repo", str(ROOT),
        "--config-dir", str(config), "--env-file", str(env),
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "(sim) geraria" in resultado.stdout
    assert "proximos passos" in resultado.stdout
    assert not config.exists() and not env.exists()
